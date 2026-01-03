"""
utility file to detect and install chrome
"""
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List
from playwright.sync_api import sync_playwright

def find_chrome_path() -> List[str]:
    system = platform.system().lower()
    paths = set()

    # see if we can find the path 
    chrome_names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]
    for name in chrome_names:
        found = shutil.which(name)
        if found:
            paths.add(found)
    
    # add in some common paths across platforms
    if system == "darwin":
        # mac
        paths.extend([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ])
    elif system == "windows":
        paths.extend([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Chromium\Application\chromium.exe",
        ])
    else:  # Linux
        paths.extend([
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ])

    # check if the paths exist
    valid_paths = []

    for p in paths:
        path_obj = Path(p)
        if path_obj.exists() and path_obj.is_file():
            valid_paths.append(p)

    return valid_paths


def install_chromium():

    try:
        subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True, # provide errors
            text=True, # allow inputs to be strings
            timeout=300, # timeout
            check=True # throw CalledProcessError  
        )
        print( find_pw_chromium_path())
    except subprocess.TimeoutExpired:
        raise RuntimeError("Chromium installation timed out")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to install chromium, error: {e}")
    except Exception as e:
        raise RuntimeError("Unexpected error occured: ", e)


def find_pw_chromium_path():
    """find path of newly installed playwrightchromium"""

    system = platform.system().lower()
    cache_dir = Path.home() / ".cache" / "ms-playwright"

    # find possible chromium directories
    chromium_dirs = list(cache_dir.glob("chromium-*"))
    if not chromium_dirs:
        return None
    print(chromium_dirs)
    # get latest download
    latest_dir = max(chromium_dirs, key=lambda p: p.stat().st_mtime)

    if system == "darwin":
        exe = latest_dir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    elif system == "windows":
        exe = latest_dir / "chrome-win" / "chrome.exe"
    else:
        exe = latest_dir / "chrome-linux" / "chrome"

    return str(exe) if exe.exists() else None

if __name__ == "__main__":
    install_chromium()