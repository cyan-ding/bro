import asyncio
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
        subprocess.Popen(
            [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "--remote-debugging-port=9222",
                "--user-data-dir=C:/tmp/chrome-profile",
            ]
        )


if __name__ == "__main__":
    asyncio.run(use_cdp())
