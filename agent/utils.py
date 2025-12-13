import json
import logging
import re

from cryptography.fernet import InvalidToken
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


def sanitize_response(response: AIMessage) -> AIMessage:
    """
    Entfernt halluzinierte Tool-Calls (z.B. wenn der Name ein ganzer Satz ist).
    Verhindert API Fehler 3280 (Invalid function name).
    """
    # Wenn keine Tool Calls da sind oder es keine AI Message ist, einfach zurückgeben
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return response

    valid_tools = []
    # Erlaubte Zeichen für Funktionsnamen: a-z, A-Z, 0-9, _, -
    name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

    for tc in response.tool_calls:
        name = tc.get("name", "")
        # Check: Ist der Name im gültigen Format und nicht zu lang?
        if name_pattern.match(name) and len(name) < 64:
            valid_tools.append(tc)
        else:
            logger.warning(f"SANITIZER: Removed invalid tool call with name: '{name}'")

    # Das manipulierte Objekt zurückgeben
    response.tool_calls = valid_tools
    return response


def decrypt_config(config, cipher_suite):
    """
    Decrypts the system_config_json from the agent configuration.
    """
    decrypted_json = "{}"
    if config.system_config_json and cipher_suite:
        try:
            decrypted_json = cipher_suite.decrypt(
                config.system_config_json.encode()
            ).decode()
        except (InvalidToken, TypeError):
            logger.warning(
                "Could not decrypt system_config_json. It might be unencrypted legacy data."
            )
            decrypted_json = config.system_config_json
    elif config.system_config_json:
        # Data exists but we have no key
        logger.error("CRITICAL: system_config_json exists but cannot be decrypted.")
        return None

    try:
        return json.loads(decrypted_json or "{}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in system_config_json after decryption.")
        return None
