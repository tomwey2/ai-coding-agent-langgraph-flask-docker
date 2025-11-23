import asyncio
import logging
import os
import shutil
import time

# LangChain Imports
# ACHTUNG: Stelle sicher, dass 'uv add langchain' ausgeführt wurde
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


# --- Lokale Tools (da der Git-MCP Server keine Dateien schreiben kann) ---
@tool
def write_to_file(filepath: str, content: str):
    """
    Writes content to a file.
    Use this to create new files or overwrite existing ones with code.
    The filepath should be relative to the current working directory.
    """
    # Sicherheits-Check: Wir wollen nicht außerhalb von work_dir schreiben
    base_dir = "/app/work_dir"
    full_path = os.path.join(base_dir, filepath)

    # Sicherstellen, dass der Ordner existiert
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"Successfully wrote to {filepath}"


# ------------------------------------------------------------------------


async def process_task_with_agent(task, config):
    """
    Der asynchrone Kern: Startet MCP, LLM und löst die Aufgabe.
    """
    repo_url = config.github_repo_url
    # Fallback, falls URL leer ist (für den Test)
    if not repo_url:
        repo_url = "https://github.com/tom-test-user/test-repo.git"  # Dummy

    work_dir = "/app/work_dir"

    # 1. MCP Adapter starten (Context Manager)
    async with McpGitAdapter() as mcp_adapter:
        logger.info("MCP Git Server connected.")

        # 2. Tools abrufen (MCP Tools + unser lokales Write-Tool)
        mcp_tools = await mcp_adapter.get_langchain_tools()
        local_tools = [write_to_file]

        all_tools = mcp_tools + local_tools

        logger.info(f"Loaded {len(all_tools)} tools (MCP Git + Local File Write).")

        # 3. LLM initialisieren
        llm = get_llm_model(config)

        # 4. Prompt definieren
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert autonomous coding agent. "
                    "You have access to Git tools via MCP and a local file writer.\n"
                    "Your goal is to solve the user's task in the provided repository.\n"
                    "Current Working Directory inside Container: {work_dir}\n"
                    "Target Repository URL: {repo_url}\n"
                    "\n"
                    "CRITICAL WORKFLOW:\n"
                    "1. git_clone the repository URL to '{work_dir}'. (If directory is not empty, assume it's already cloned or handle errors).\n"
                    "2. Analyze the file structure (you can rely on git tools or just overwrite files).\n"
                    "3. Use 'write_to_file' to implement the requested changes.\n"
                    "4. git_add the changed files.\n"
                    "5. git_commit with a descriptive message.\n"
                    "6. git_push (Assume credentials are set via global config or environment).\n"
                    "7. Reply with 'DONE' and a summary of what you did.",
                ),
                (
                    "human",
                    "Task ID: {task_id}\nTitle: {title}\nDescription: {description}",
                ),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        # 5. Agent zusammenbauen
        # Mistral unterstützt Tool-Calling nativ, daher passt create_tool_calling_agent perfekt
        agent = create_tool_calling_agent(llm, all_tools, prompt)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=all_tools,
            verbose=True,
            handle_parsing_errors=True,  # Falls Mistral mal komisches JSON spuckt
        )

        # 6. Ausführen!
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
    """Der Entrypoint für den Scheduler (Synchron)."""
    with app.app_context():
        try:
            config = AgentConfig.query.first()
            if not config or not config.is_active:
                return

            logger.info("Agent cycle starting...")

            # Connector Setup
            connector = TaskAppConnector(
                base_url=config.task_app_base_url,
                username=config.agent_username,
                password=config.agent_password,
                project_id=config.target_project_id,
            )

            # Tasks holen
            tasks = connector.get_open_tasks()
            if not tasks:
                logger.info("No open tasks found.")
                return

            # Wir bearbeiten nur den ersten Task
            task = tasks[0]
            logger.info(f"Processing Task ID: {task['id']}")

            # Kommentar: "Ich fange an"
            connector.post_comment(
                task["id"], "🤖 Agent V2 (MCP & Mistral) started working..."
            )

            # Work Dir vorbereiten (Clean Slate optional)
            if not os.path.exists("/app/work_dir"):
                os.makedirs("/app/work_dir")

            # --- ASYNC AGENT STARTEN ---
            try:
                # Hier rufen wir die asynchrone Logik auf
                output = asyncio.run(process_task_with_agent(task, config))

                final_comment = f"🤖 Job Done.\n\nAgent Output:\n{output}"
                new_status = "IN_REVIEW"

            except Exception as e:
                logger.error(f"Agent failed: {e}", exc_info=True)
                final_comment = f"💥 Agent crashed: {str(e)}"
                new_status = "OPEN"

            # Abschluss
            connector.post_comment(task["id"], final_comment)

            if new_status == "IN_REVIEW":
                connector.update_status(task["id"], new_status)

            logger.info("Agent cycle finished.")

        except Exception as e:
            logger.error(f"Unexpected error in agent cycle: {e}", exc_info=True)
