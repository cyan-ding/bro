import asyncio
import os
import sys
import subprocess
import urllib.error
import urllib.request


async def use_cdp() -> None:
    def is_chrome_running():
        try:
            with urllib.request.urlopen(
                "http://localhost:9222/json", timeout=2
            ) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False


    if not is_chrome_running():
        if sys.platform == "darwin":
            # macOS default Chrome path
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            user_data_dir = os.path.expanduser("~/tmp/chrome-profile")
        else:
            # Windows default Chrome path
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            user_data_dir = "C:/tmp/chrome-profile"

        subprocess.Popen(
            [
                chrome_path,
                "--remote-debugging-port=9222",
                f"--user-data-dir={user_data_dir}",
            ]
        )


if __name__ == "__main__":
    asyncio.run(use_cdp())
