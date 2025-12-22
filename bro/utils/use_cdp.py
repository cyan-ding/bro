import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

# Global variable to track the Chrome subprocess
_chrome_process: Optional[subprocess.Popen] = None
_chrome_running: bool = False


def use_cdp() -> None:
    def is_chrome_running():
        try:
            with urllib.request.urlopen(
                "http://localhost:9222/json", timeout=2
            ) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False

    global _chrome_process

    if not is_chrome_running():
        print("Starting Chrome with CDP...")
        if sys.platform == "darwin":
            # macOS default Chrome path
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            user_data_dir = os.path.expanduser("~/tmp/chrome-profile")
        else:
            # Windows default Chrome path
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            user_data_dir = "C:/tmp/chrome-profile"

        _chrome_process = subprocess.Popen(
            [
                chrome_path,
                "--remote-debugging-port=9222",
                f"--user-data-dir={user_data_dir}",
            ],
            creationflags=134217728,
        )

        for _ in range(30):
            time.sleep(1)
            if is_chrome_running():
                break

        if is_chrome_running():
            print("✅ Chrome is running with CDP enabled")
        else:
            print("❌ Failed to start Chrome with CDP after 30 seconds")
            raise TimeoutError
    else:
        print("✅ Chrome is already running with CDP enabled")


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
        print("Closing Chrome subprocess...")
        _chrome_process.terminate()

        # Wait for process to terminate gracefully
        try:
            _chrome_process.wait(timeout=5)
            print("✅ Chrome subprocess terminated successfully")
        except subprocess.TimeoutExpired:
            print("⚠️ Chrome didn't terminate gracefully, forcing kill...")
            _chrome_process.kill()
            _chrome_process.wait()
            print("✅ Chrome subprocess killed")

        _chrome_process = None
        return True

    except Exception as e:
        print(f"❌ Error closing Chrome subprocess: {e}")
        return False


if __name__ == "__main__":
    use_cdp()
