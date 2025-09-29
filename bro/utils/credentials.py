"""
Credential management utilities for Bro web interaction agent.

This module contains functions for handling user credentials using JSON storage.

@file purpose: Provides credential management utilities for Bro
"""

import json
from pathlib import Path
from typing import Optional

# In-process counter to detect repeated credential fetch attempts
_credential_request_counts: dict[str, int] = {}


async def get_credentials(placeholder: str) -> Optional[str]:
    """
    Retrieve or update a credential value for a given placeholder from `credentials.json`.

    Behavior:
    - If the placeholder does not exist, prompt the user for a value and save it.
    - If called multiple times for the same placeholder (repeat attempt), force refresh.

    Args:
        placeholder: The placeholder key (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD').

    Returns:
        The credential value if found and non-empty; otherwise None.
    """
    print("Retrieving credentials...")
    credentials_file = Path("credentials.json")

    # Initialize empty credentials file if it doesn't exist
    if not credentials_file.exists():
        credentials_file.write_text("{}")

    # Load credentials from JSON
    try:
        credentials: dict[str, str] = json.loads(credentials_file.read_text())
    except (json.JSONDecodeError, PermissionError) as e:
        print(f"Error reading credentials file: {e}")
        credentials = {}

    # Track repeated attempts within the same process
    count = _credential_request_counts.get(placeholder, 0) + 1
    _credential_request_counts[placeholder] = count
    is_repeat_attempt = count > 1

    # Return existing credential if no retry needed and not a repeat attempt
    if not is_repeat_attempt:
        if placeholder in credentials and credentials[placeholder]:
            return credentials[placeholder]

    # Prompt for new or updated value
    prompt_msg = (
        f"Incorrect or updated credentials required, please enter NEW value for {placeholder}: "
        if is_repeat_attempt
        else f"No credentials detected, please input {placeholder}: "
    )
    print(prompt_msg)

    try:
        value = input(f"Enter value for {placeholder}: ").strip()
    except Exception:
        value = ""

    if not value:
        print("No value provided.")
        return None

    # Update credentials and save to file
    credentials[placeholder] = value
    try:
        credentials_file.write_text(json.dumps(credentials, indent=2))
    except (PermissionError, OSError) as e:
        print(f"Error saving credential to file: {e}")
        return None

    return value
