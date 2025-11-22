import logging
import time

from flask import current_app

from agent.task_connector import TaskAppConnector
from extensions import db
from models import AgentConfig
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def run_agent_cycle():
    """
    This function is executed by the scheduler.
    It fetches the configuration, connects to the TaskApp, and processes tasks.
    Flask-APScheduler should provide the necessary application context.
    """
    logging.info("Agent cycle starting...")

    # The app context is required to interact with the database.
    # Flask-APScheduler is configured to provide this automatically.
    config = AgentConfig.query.first()

    if not config:
        logging.warning("Agent configuration not found in database. Skipping cycle.")
        return

    if not config.is_active:
        logging.info("Agent is not active. Skipping cycle.")
        return

    logging.info(
        f"Agent is active. Polling interval: {config.polling_interval_seconds}s. Target: {config.task_app_base_url}"
    )

    connector = TaskAppConnector(
        base_url=config.task_app_base_url, api_token=config.api_token
    )

    tasks = connector.get_open_tasks()

    if tasks is None:
        logging.error("Could not retrieve tasks from the API. Ending cycle.")
        return

    if not tasks:
        logging.info("No open tasks found.")
        return

    # For Phase 1, we only process the first task found.
    task_to_process = tasks[0]
    task_id = task_to_process.get("id")

    if not task_id:
        logging.error("Found a task without an 'id'. Skipping.")
        return

    logging.info(f"Processing task ID: {task_id}")

    # --- Simulation Step ---
    # 1. Post a starting comment
    success = connector.post_comment(task_id, "Agent simulation started.")
    if not success:
        logging.error(f"Failed to post 'start' comment for task {task_id}. Aborting.")
        return

    # 2. "Work" for 2 seconds
    logging.info("Simulating work for 2 seconds...")
    time.sleep(2)

    # 3. Post a finishing comment and update status
    success = connector.post_comment(task_id, "Agent simulation finished.")
    if success:
        logging.info("Successfully posted 'finish' comment.")
        status_updated = connector.update_status(task_id, "IN_REVIEW")
        logging.info("Successfully posted 'finish' comment.")
        status_updated = connector.update_status(task_id, 'IN_REVIEW')
        if status_updated:
            logging.info(f"Successfully updated task {task_id} status to 'IN_REVIEW'.")
        else:
            logging.error(f"Failed to update status for task {task_id}.")
    else:
        logging.error(f"Failed to post 'finish' comment for task {task_id}.")

    logging.info("Agent cycle finished.")
