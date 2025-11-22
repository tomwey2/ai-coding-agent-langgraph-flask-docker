import logging

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class TaskAppConnector:
    """
    A connector class to interact with the external TaskApp API.
    """

    def __init__(self, base_url, api_token=None):
        if not base_url:
            raise ValueError("base_url cannot be empty.")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    def _get_url(self, path):
        return f"{self.base_url}{path}"

    def get_open_tasks(self):
        """Fetches tasks with status 'open'."""
        try:
            url = self._get_url("/tasks?status=open")
            logging.info(f"Fetching open tasks from {url}")
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed for get_open_tasks: {e}")
            return None

    def post_comment(self, task_id, comment):
        """Posts a comment to a specific task."""
        if not task_id or not comment:
            logging.warning("task_id and comment cannot be empty for post_comment.")
            return False
        try:
            url = self._get_url(f"/tasks/{task_id}/comments")
            payload = {"comment": comment}
            logging.info(f"Posting comment to {url}: '{comment}'")
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed for post_comment on task {task_id}: {e}")
            return False

    def update_status(self, task_id, status):
        """Updates the status of a specific task using PATCH."""
        if not task_id or not status:
            logging.warning("task_id and status cannot be empty for update_status.")
            return False
        try:
            url = self._get_url(f"/tasks/{task_id}")
            payload = {"status": status}
            logging.info(f"Updating status of task {task_id} to '{status}' at {url}")
            # Using PATCH is standard for partial updates.
            response = requests.patch(
                url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(
                f"API request failed for update_status on task {task_id}: {e}"
            )
            logging.error(f"API request failed for update_status on task {task_id}: {e}")
            return False
