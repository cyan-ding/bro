"""
@file purpose: Launches a browser instance and evaluates the JavaScript code from test_buildDomTree.js in a web page context using Playwright (async version).
This script is intended for testing the DOM tree builder logic in a real browser environment.
"""

import asyncio
from patchright.async_api import async_playwright, Page
from pathlib import Path
import re

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

async def main() -> None:
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
		)
		page = await browser.new_page()
		try:
			await page.goto(
				# google form test
				# "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform"
				# google doc test
				# "https://docs.google.com/document/d/1DBPuFb-byQ9rZcxZo2ky0y5Sn1TjeF-2q6rfwOhI1sg/edit?usp=sharing"
				# google sheets test
				# "https://docs.google.com/spreadsheets/d/1seBguBzuDMYo6-7vZCOlb-Y6zFKTKKUYqJu81qxev6Q/edit?usp=sharing"
				# iframe test
				"https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe",
				wait_until="domcontentloaded",
			)
		except Exception as e:
			print("Browser timed out:", e)
			await browser.close()
			return

		# read from cache file
		# Inject the bundled JS code
		await page.evaluate(js_bundle)

		# Call window.buildDomTree with arguments
		result = await page.evaluate(
			"(args) => window.buildDomTree(args)",
			{
				"doHighlightElements": True,
				"debugMode": True,
				"overlapThreshold": 0.4,
			},
		)

		await page.wait_for_timeout(10000)
		await page.screenshot(path="actions/new/screenshot.png")
		# input_elements = [el for el in result['highlightedElements'] if el.get('index') == 135]
		#print(input_elements)
		print(result['map'])
		await browser.close()

if __name__ == "__main__":
	asyncio.run(main())
