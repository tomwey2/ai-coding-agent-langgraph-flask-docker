"""
This module defines the mappings for different task management systems.
It provides a centralized way to configure the commands, tools, and parsers
for each supported system.
"""

import logging

logger = logging.getLogger(__name__)


def extract_cards(data):
    """
    Extracts all cards from a Trello board object into a flat list.
    The data from read_board is a dictionary, where the 'lists' key
    contains the lists and their cards.
    """
    logger.info("Extracting data from Trello: %s", data)
    if not isinstance(data, dict) or "lists" not in data:
        return []

    all_cards = []
    for trello_list in data.get("lists", []):
        if isinstance(trello_list, dict) and "cards" in trello_list:
            logger.info("Extracting cards from list: %s", trello_list["cards"])
            all_cards.extend(trello_list["cards"])
    return all_cards


# A lambda function to parse the Trello card format into our canonical task format
trello_response_parser = lambda data: [
    {
        "id": card.get("id"),
        "title": card.get("name"),
        "description": card.get("desc"),
    }
    for card in extract_cards(data)
]

SYSTEM_DEFINITIONS = {
    "TRELLO": {
        "command": ["tsx", "/app/servers/trello/src/index.ts"],
        "polling_tool": "read_board",
        "polling_args": {"boardId": "{trello_todo_list_id}"},
        "response_parser": trello_response_parser,
    },
    # Future systems like JIRA can be added here
    # "JIRA": {
    #     "command": ["npx", "-y", "@modelcontextprotocol/server-jira"],
    #     "polling_tool": "get_issues_in_project",
    #     "polling_args": {"projectId": "{project_id}"},
    #     "response_parser": lambda issue: {
    #         "id": issue.get("key"),
    #         "title": issue.get("fields", {}).get("summary"),
    #         "description": issue.get("fields", {}).get("description"),
    #     },
    # },
}
