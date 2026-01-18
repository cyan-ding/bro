"""
Environment variable loader with proper precedence.

Loads environment variables from .bro/.env:
1. System environment variables (highest priority - already set, won't be overridden)
2. ~/.bro/.env (user-provided keys from Electron app)
"""

from pathlib import Path
from dotenv import load_dotenv


def load_env_files() -> None:
    """
    Load environment variables with proper precedence.
    
    This function should be called before accessing any environment variables
    to ensure user-provided keys override development keys, but system
    environment variables always take precedence.
    """
    user_env = Path.home() / ".bro" / ".env"
    if user_env.exists():
        load_dotenv(user_env, override=True)
