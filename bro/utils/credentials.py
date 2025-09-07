"""
Credential management utilities for Bro web interaction agent.

This module contains functions for handling user credentials,
including reading from files and fuzzy matching.

@file purpose: Provides credential management utilities for Bro
"""

import difflib
from pathlib import Path
from typing import Optional

# In-process counter to detect repeated credential fetch attempts
_credential_request_counts: dict[str, int] = {}


async def get_credentials(placeholder: str, retry_login: bool = False) -> Optional[str]:
    """
    Retrieve or update a credential value for a given placeholder from `credentials.txt`.

    Behavior:
    - If `retry_login` is False and a non-empty value exists, return it.
    - If `retry_login` is True and the placeholder exists, prompt the user for a NEW value,
      overwrite the existing value in `credentials.txt`, and return it.
    - If the placeholder does not exist (or is empty), prompt the user for a value and
      write it to `credentials.txt`.
    - Fallback: If the LLM forgets to set `retry_login=True` but this function is called
      multiple times for the same placeholder within the same run (repeat attempt), this
      function will prompt for a NEW value and overwrite the existing one.

    Args:
        placeholder: The placeholder key (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD').
        retry_login: When True, force prompting for a new value and persist the update.

    Returns:
        The credential value if found and non-empty; otherwise None.
    """
    print("Retrieving credentials...")
    credentials_file = Path("credentials.txt")

    if not credentials_file.exists():
        credentials_file.write_text(
            "# Sample credentials file for Bro\n"
            "# Each line is PLACEHOLDER=actual_value\n"
            "# Example: GOOGLE_EMAIL=example@gmail.com\n"
            "#\n"
        )
        print(f"No credentials detected, please input {placeholder}: ")
        value = input(f"Enter value for {placeholder}: ").strip()
        if value:
            with open(credentials_file, "a", encoding="utf-8") as f:
                f.write(f"{placeholder}={value}\n")
            return value
        else:
            print("No value provided, exiting.")
            return None

    # Load credentials, skipping commented/blank lines
    credentials: dict[str, str] = {}
    try:
        with open(credentials_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    credentials[key.strip()] = value.strip()
    except (FileNotFoundError, PermissionError) as e:
        print(f"Error reading credentials file: {e}")
        return None

    # Track repeated attempts within the same process
    count = _credential_request_counts.get(placeholder, 0) + 1
    _credential_request_counts[placeholder] = count
    is_repeat_attempt = count > 1

    # Prefer exact match when present and non-empty, unless retry requested
    if not retry_login:
        # Fallback: if we are attempting again in the same run and a value exists, force refresh
        if (
            is_repeat_attempt
            and placeholder in credentials
            and credentials[placeholder] != ""
        ):
            pass  # Intentionally fall through to prompting for a NEW value below
        else:
            # exact match
            if placeholder in credentials and credentials[placeholder] != "":
                return credentials[placeholder]
            else:
                # Fuzzy match with tolerance, only if it yields a non-empty value
                matches = difflib.get_close_matches(
                    placeholder, credentials.keys(), n=1, cutoff=0.6
                )
                if matches:
                    matched_key = matches[0]
                    if credentials.get(matched_key):
                        return credentials[matched_key]

                # if this is a new credential, prompt for a new value
                print(f"No credentials detected, please input {placeholder}: ")
                value = input(f"Enter value for {placeholder}: ").strip()
                if value:
                    with open(credentials_file, "a", encoding="utf-8") as f:
                        f.write(f"{placeholder}={value}\n")
                    return value
                else:
                    print("No value provided, exiting.")
                    return None

    # Prompt for new value
    print(
        f"Incorrect or updated credentials required, please enter NEW value for {placeholder}: "
    )
    try:
        value = input(f"Enter value for {placeholder}: ").strip()
    except Exception:
        value = ""
    if value:
        # Update existing line for the placeholder if present; otherwise append
        try:
            lines: list[str] = []
            found = False
            with open(credentials_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    if key.strip() == placeholder:
                        lines[i] = f"{placeholder}={value}\n"
                        found = True
                        break
            if not found:
                lines.append(f"{placeholder}={value}\n")
            with open(credentials_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except (PermissionError, OSError) as e:
            print(f"Error saving credential to file: {e}")
            return None
        return value
    print("No value provided, skipping credential update.")
    return None
