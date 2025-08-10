"""
Credential management utilities for Bro web interaction agent.

This module contains functions for handling user credentials,
including reading from files and fuzzy matching.

@file purpose: Provides credential management utilities for Bro
"""

import difflib
from pathlib import Path
from typing import Optional


async def get_credentials(placeholder: str) -> Optional[str]:
    """
    Get credentials from the credentials file based on placeholder.

    Args:
        placeholder: The placeholder string (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD')

    Returns:
        The credential value if found, None otherwise
    """
    print("Retrieving credentials...")
    credentials_file = Path("credentials.txt")
    if not credentials_file.exists():
        print(
            "No credentials detected, generating file. Please fill in credentials before proceeding."
        )
        credentials_file.write_text(
            "# Sample credentials file for Bro\n"
            "# Format: PLACEHOLDER=actual_value\n"
            "# \n"
        )
        value = input(f"Enter value for {placeholder}: ").strip()
        if value:
            with open(credentials_file, "a", encoding="utf-8") as f:
                f.write(f"{placeholder}={value}\n")
            return value
        return None

    credentials = {}
    try:
        with open(credentials_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    credentials[key.strip()] = value.strip()
    except (FileNotFoundError, PermissionError) as e:
        print(f"Error reading credentials file: {e}")
        return None

    # Use fuzzy matching to locate the closest key in credentials for the given placeholder
    if placeholder in credentials:
        return credentials[placeholder]
    # Find the closest match using difflib
    matches = difflib.get_close_matches(
        placeholder, credentials.keys(), n=1, cutoff=0.6
    )
    if matches:
        return credentials[matches[0]]
    return None
