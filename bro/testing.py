"""
@file purpose: Launches a browser instance and evaluates the JavaScript code from test_buildDomTree.js in a web page context using Playwright (async version).
This script is intended for testing the DOM tree builder logic in a real browser environment.
"""

import asyncio
import re
import subprocess
import socket
import sys
from pathlib import Path

# Ensure we can import agent utilities from this script
sys.path.append(str(Path(__file__).parent))
from agent.action_utils import format_elements_text
from patchright.async_api import async_playwright


def create_js_bundle() -> str:
    """
    Reads all JS modules, removes their import/export statements, and combines them
    into a single string, wrapped in an IIFE to expose `buildDomTree` on the window object.
    This creates a self-contained, injectable script for Playwright.
    """
    base_path = Path(__file__).parent / "dom"
    files_in_order = ["metrics.js", "highlight.js", "dom_utils.js", "buildDomTree.js"]

    full_code = []
    for file_name in files_in_order:
        file_path = base_path / file_name
        code = file_path.read_text(encoding="utf-8")
        # A more robust way to remove import/export statements
        code = re.sub(r"^\s*import .*from .*", "", code, flags=re.MULTILINE)
        code = re.sub(r"^\s*export (default )?", "", code, flags=re.MULTILINE)
        full_code.append(code)

    # Wrap in an IIFE to expose the main function
    bundle = f"""
	(() => {{
		{"".join(full_code)}
		window.buildDomTree = buildDomTree;
	}})();
	"""
    return bundle


def is_cdp_running(host="127.0.0.1", port=9222):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


async def test_cdp() -> None:
    # Launch Chrome with CDP port
    subprocess.Popen(
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-port=9222",
            "--user-data-dir=C:/tmp/chrome-profile",
        ]
    )

    await asyncio.sleep(2)  # Give Chrome time to start

    # if not is_cdp_running():
    #     subprocess.Popen([
    #         r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    #         "--remote-debugging-port=9222",
    #         "--user-data-dir=C:/tmp/chrome-profile"
    #     ])

    js_bundle = create_js_bundle()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # List contexts (Chrome profiles)
        contexts = browser.contexts
        if contexts:
            context = contexts[0]  # Use existing profile
        else:
            context = await browser.new_context()  # Or create new

        # Open a new tab
        page = await context.new_page()
        await page.goto(
            # google form test
            # "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform",
            # google doc test
            "https://docs.google.com/document/d/1DBPuFb-byQ9rZcxZo2ky0y5Sn1TjeF-2q6rfwOhI1sg/edit?usp=sharing",
            # google sheets test
            # "https://docs.google.com/spreadsheets/d/1seBguBzuDMYo6-7vZCOlb-Y6zFKTKKUYqJu81qxev6Q/edit?usp=sharing",
            # iframe test
            # "https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe",
            # sticky element test
            # "https://en.wikipedia.org/wiki/English_Wikipedia",
            wait_until="domcontentloaded",
        )
        # Inject the bundled JS code
        await page.evaluate(js_bundle)

        # Call window.buildDomTree with arguments
        result = await page.evaluate(
            "(args) => window.buildDomTree(args)",
            {
                "doHighlightElements": True,
                "debugMode": True,
                "overlapThreshold": 0.7,
                "indexByPosition": True,
            },
        )
        await page.wait_for_timeout(50000)
        await page.screenshot(path="bro/screenshot.png")
        print("Raw highlightedElements:", result.get("highlightedElements"))
        # Test the new Python formatter with the serialized elements
        serialized = result.get("highlightedElementsSerialized", [])
        formatted = await format_elements_text(serialized)
        print("\nFormatted elements (inspiration style):\n")
        print(formatted)
        await page.wait_for_timeout(50000)
        await browser.close()  # Closes connection, not Chrome itself


async def test_no_cdp() -> None:
    """
    Launches a Chromium browser, navigates to a target page, injects the bundled JS code,
    and calls window.buildDomTree().
    """
    js_bundle = create_js_bundle()

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
            # Uncomment the line below to automatically open DevTools
            # devtools=True,
        )
        page = await browser.new_page()
        try:
            await page.goto(
                # google form test
                # "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform",
                # google doc test
                # "https://docs.google.com/document/d/1DBPuFb-byQ9rZcxZo2ky0y5Sn1TjeF-2q6rfwOhI1sg/edit?usp=sharing",
                # google sheets test
                # "https://docs.google.com/spreadsheets/d/1seBguBzuDMYo6-7vZCOlb-Y6zFKTKKUYqJu81qxev6Q/edit?usp=sharing",
                # iframe test
                "https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe",
                # sticky element test
                # "https://en.wikipedia.org/wiki/English_Wikipedia",
                wait_until="domcontentloaded",
            )
        except Exception as e:
            print("Browser timed out, trying to open DevTools:", e)

        # read from cache file
        # Inject the bundled JS code
        await page.evaluate(js_bundle)

        # Call window.buildDomTree with arguments
        result = await page.evaluate(
            "(args) => window.buildDomTree(args)",
            {
                "doHighlightElements": True,
                "debugMode": True,
                "overlapThreshold": 0.7,
                "indexByPosition": True,
            },
        )
        await page.wait_for_timeout(50000)
        await page.screenshot(path="bro/screenshot.png")
        print("Raw highlightedElements:", result.get("highlightedElements"))
        # Test the new Python formatter with the serialized elements
        serialized = result.get("highlightedElementsSerialized", [])
        formatted = await format_elements_text(serialized)
        print("\nFormatted elements (inspiration style):\n")
        print(formatted)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_cdp())
