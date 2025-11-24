import asyncio
import logging
import os
import shutil
import subprocess  # <--- WICHTIG: Für den System-Clone
import time

# LangChain Imports
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agent.llm_setup import get_llm_model
from agent.mcp_adapter import McpGitAdapter
from agent.task_connector import TaskAppConnector

# Unsere Module
from extensions import db
from models import AgentConfig

logger = logging.getLogger(__name__)


# --- Lokale Tools ---
@tool
def write_to_file(filepath: str, content: str):
    """
    Writes content to a file.
    Use this to create new files or overwrite existing ones with code.
    The filepath should be relative to the current working directory.
    """
    base_dir = "/app/work_dir"
    full_path = os.path.join(base_dir, filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote to {filepath}"


# --- BOOTSTRAPPING FUNKTION ---
def ensure_repository_exists(repo_url, work_dir):
    """
    Stellt sicher, dass work_dir ein valides Git-Repo ist,
    DAMIT der MCP-Server überhaupt starten kann.
    """
    # 1. Ordner erstellen
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)

    # 2. Prüfen ob .git existiert
    git_dir = os.path.join(work_dir, ".git")
    if os.path.isdir(git_dir):
        logger.info("Repository already exists. Skipping clone.")
        return

    logger.info(f"Bootstrapping repository from {repo_url}...")

    # 3. Versuchen zu Clonen
    try:
        # Wir nutzen "." um in den aktuellen Ordner zu clonen
        subprocess.run(
            ["git", "clone", repo_url, "."],
            cwd=work_dir,
            check=True,
            capture_output=True,
        )
        logger.info("Clone successful.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Git Clone failed (likely Auth or Empty URL): {e}")
        logger.warning("Falling back to 'git init' so the Agent can at least start.")

        # 4. Fallback: Leeres Repo initialisieren (damit MCP nicht crasht)
        subprocess.run(["git", "init"], cwd=work_dir, check=True)


# ------------------------------------------------------------------------


async def process_task_with_agent(task, config):
    repo_url = (
        config.github_repo_url or "https://github.com/tom-test-user/test-repo.git"
    )
    work_dir = "/app/work_dir"

    # SCHRITT 0: Bootstrapping (Henne-Ei-Problem lösen)
    # Wir machen das synchron, bevor der MCP Server startet
    ensure_repository_exists(repo_url, work_dir)

    # SCHRITT 1: MCP Adapter starten
    # Jetzt ist work_dir garantiert ein Git-Repo, der Server wird nicht crashen.
    async with McpGitAdapter() as mcp_adapter:
        logger.info("MCP Git Server connected.")

        mcp_tools = await mcp_adapter.get_langchain_tools()
        local_tools = [write_to_file]
        all_tools = mcp_tools + local_tools

        llm = get_llm_model(config)

        # Prompt Update: Wir sagen dem Agenten NICHT mehr "Clone repo",
        # weil wir das schon erledigt haben. Er soll "Analysieren" und "Coden".
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert autonomous coding agent with file system access.\n"
                    "You are working in a Linux container. The repository is cloned at: {work_dir}\n"
                    "Target Repository URL: {repo_url}\n"
                    "\n"
                    "AVAILABLE TOOLS:\n"
                    "- use 'write_to_file' to save content to disk.\n"
                    "- use 'git_add', 'git_commit', 'git_push' for version control.\n"
                    "\n"
                    "RULES:\n"
                    "1. DO NOT just output the code or text in the chat. That is useless.\n"
                    "2. YOU MUST call 'write_to_file' to actually save your changes to the disk.\n"
                    "3. If you generate a README or code, save it immediately using the tool.\n"
                    "4. After saving, you MUST commit and push.\n"
                    "\n"
                    "WORKFLOW:\n"
                    "1. Analyze the current files.\n"
                    "2. Generate the new content.\n"
                    '3. EXECUTE \'write_to_file(filepath="README.md", content="...")\'.\n'
                    "4. EXECUTE 'git_add(path=\".\")'.\n"
                    "5. EXECUTE 'git_commit(message=\"Update README\")'.\n"
                    "6. Reply with 'DONE' only after the tools have run.",
                ),
                (
                    "human",
                    "Task ID: {task_id}\nTitle: {title}\nDescription: {description}",
                ),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_tool_calling_agent(llm, all_tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent, tools=all_tools, verbose=True, handle_parsing_errors=True
        )

        logger.info(f"Agent starts working on Task {task['id']}...")
        result = await agent_executor.ainvoke(
            {
                "work_dir": work_dir,
                "repo_url": repo_url,
                "task_id": task["id"],
                "title": task.get("title", ""),
                "description": task.get("description", "No description provided."),
            }
        )

        return result["output"]


def run_agent_cycle(app):
    # from main import app  # Local import to avoid circular dependency

    with app.app_context():
        try:
            config = AgentConfig.query.first()
            if not config or not config.is_active:
                return

            logger.info("Agent cycle starting...")

            connector = TaskAppConnector(
                base_url=config.task_app_base_url,
                username=config.agent_username,
                password=config.agent_password,
                project_id=config.target_project_id,
            )

            tasks = connector.get_open_tasks()
            if not tasks:
                logger.info("No open tasks found.")
                return

            task = tasks[0]
            logger.info(f"Processing Task ID: {task['id']}")

            connector.post_comment(
                task["id"], "🤖 Agent V2 (MCP & Mistral) started working..."
            )

            try:
                # Async Logik starten
                output = asyncio.run(process_task_with_agent(task, config))
                # --- UPDATE: Großzügiges Limit dank TEXT Feld ---
                # 4000 Zeichen sind etwa eine volle A4 Seite Text.
                limit = 4000
                if len(output) > limit:
                    short_output = (
                        output[:limit] + f"\n\n... (Output truncated at {limit} chars)"
                    )
                else:
                    short_output = output
                final_comment = (
                    f"🤖 Job Done. I updated the code.\n\nSummary:\n{short_output}"
                )
                new_status = "In Review"

            except Exception as e:
                logger.error(f"Agent failed: {e}", exc_info=True)
                final_comment = f"💥 Agent crashed: {str(e)}"
                new_status = "OPEN"

            connector.post_comment(task["id"], final_comment)
            if new_status == "IN_REVIEW":
                connector.update_status(task["id"], new_status)

            logger.info("Agent cycle finished.")

        except Exception as e:
            logger.error(f"Unexpected error in agent cycle: {e}", exc_info=True)
