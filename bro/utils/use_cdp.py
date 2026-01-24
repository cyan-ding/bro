import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from bro.utils.config import UserSettings

# Global variable to track the Chrome subprocess
_chrome_process: Optional[subprocess.Popen] = None
_chrome_running: bool = False


def use_cdp() -> None:
    """Start Chrome with CDP enabled using the path from UserSettings."""
    def is_chrome_running() -> bool:
        try:
            with urllib.request.urlopen(
                "http://localhost:9222/json", timeout=2
            ) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False

    global _chrome_process

    if not is_chrome_running():
        # Get Chrome path from UserSettings (guaranteed to exist from onboarding)
        settings = UserSettings.load()
        if not settings.chrome_path:
            raise RuntimeError(
                "Chrome path not configured. Please complete onboarding."
            )
        
        chrome_path = Path(settings.chrome_path)
        if not chrome_path.exists():
            raise RuntimeError(
                f"Chrome executable not found at: {chrome_path}. "
                "Please update your Chrome path in settings."
            )
        
        # Determine user data directory (platform-agnostic)
        user_data_dir = os.path.expanduser("~/tmp/chrome-profile")
        
        # Prepare subprocess arguments
        subprocess_args = [
            str(chrome_path),
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
        ]
        
        # Windows-specific: creationflags to prevent new console window
        system = platform.system().lower()
        if system == "windows":
            # CREATE_NO_WINDOW = 0x08000000
            _chrome_process = subprocess.Popen(
                subprocess_args,
                creationflags=0x08000000,
            )
        else:
            _chrome_process = subprocess.Popen(
                subprocess_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Wait for Chrome to start
        for _ in range(30):
            time.sleep(1)
            if is_chrome_running():
                break

        if not is_chrome_running():
            print("❌ Failed to start Chrome with CDP after 30 seconds")
            raise TimeoutError("Chrome failed to start with CDP")


def close_chrome() -> bool:
    """
    Close the Chrome browser subprocess if it was started by use_cdp.

    Returns:
        True if Chrome was closed, False if no Chrome process was tracked
    """
    global _chrome_process

    if _chrome_process is None:
        print("⚠️ No Chrome process tracked - browser may have been started externally")
        return False

    try:
        _chrome_process.terminate()

        # Wait for process to terminate gracefully
        try:
            _chrome_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("⚠️ Chrome didn't terminate gracefully, forcing kill...")
            _chrome_process.kill()
            _chrome_process.wait()

        _chrome_process = None
        return True

    except Exception as e:
        print(f"❌ Error closing Chrome subprocess: {e}")
        return False


if __name__ == "__main__":
    use_cdp()
