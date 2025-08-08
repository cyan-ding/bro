"""
@file purpose: Tests the shadow DOM extraction JavaScript code in a web page context using Playwright.
This script is intended for testing the shadow DOM extraction logic in a real browser environment.
"""

import asyncio
from patchright.async_api import async_playwright
from pathlib import Path


async def main() -> None:
    """
    Launches a Chromium browser, navigates to a target page, injects the shadow DOM extraction JS code,
    and calls the shadow DOM extraction functions.
    """
    # Read the shadow DOM extraction script
    shadow_dom_path = Path(__file__).parent / "extract_shadow_dom_best.js"
    shadow_dom_code = shadow_dom_path.read_text(encoding="utf-8")

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
                # Test pages with shadow DOM
                "https://developer.mozilla.org/en-US/docs/Web/Web_Components/Using_shadow_DOM",  # MDN shadow DOM docs
                # "https://webcomponents.dev/",  # Web Components playground
                # "https://lit.dev/",  # Lit framework (uses shadow DOM)
                # "https://stenciljs.com/",  # Stencil framework (uses shadow DOM)
                wait_until="domcontentloaded",
            )
        except Exception as e:
            print("Browser timed out:", e)
            await browser.close()
            return

        # Inject the shadow DOM extraction script
        await page.evaluate(shadow_dom_code)

        # Test basic shadow host finding
        print("Testing basic shadow host finding:")
        try:
            hosts_result = await page.evaluate("() => window.findShadowHosts()")
            print(f"findShadowHosts found {len(hosts_result)} shadow hosts:")
            for host in hosts_result:
                print(
                    f"  - {host['tagName']} (class: {host['className']}, id: {host['id']})"
                )
        except Exception as e:
            print(f"Error in findShadowHosts: {e}")

        # Test detailed shadow DOM extraction
        print("\nTesting detailed shadow DOM extraction:")
        try:
            detailed_result = await page.evaluate(
                "() => window.findShadowHostsDetailed()"
            )
            print(f"findShadowHostsDetailed found {len(detailed_result)} shadow hosts:")
            for shadow in detailed_result:
                print(
                    f"  - {shadow['tagName']} (id: {shadow['id']}, mode: {shadow['shadowRoot']['mode']})"
                )
                if shadow["shadowRoot"]["innerHTML"]:
                    print(
                        f"    Content length: {len(shadow['shadowRoot']['innerHTML'])}"
                    )
                    print(
                        f"    Text content: {shadow['shadowRoot']['textContent'][:100]}..."
                    )
                else:
                    print("    No content found")
        except Exception as e:
            print(f"Error in findShadowHostsDetailed: {e}")

        # Test shadow DOM summary extraction
        print("\nTesting shadow DOM summary extraction:")
        try:
            summary_result = await page.evaluate(
                "() => window.extractShadowDOMBestSummary()"
            )
            print(f"Total shadow roots found: {summary_result['totalShadowRoots']}")
            if summary_result["summary"]:
                print("Shadow DOM elements found:")
                for shadow in summary_result["summary"]:
                    print(
                        f"  - {shadow['hostTag']} (class: {shadow['hostClass']}, id: {shadow['hostId']}, mode: {shadow['shadowMode']}, children: {shadow['shadowChildrenCount']})"
                    )
            else:
                print("No shadow DOM elements found on this page")
        except Exception as e:
            print(f"Error in extractShadowDOMBestSummary: {e}")

        # Test with findShadowHosts for comparison
        print("\nTesting findShadowHosts for comparison:")
        try:
            hosts_result = await page.evaluate("() => window.findShadowHosts()")
            print(f"findShadowHosts found {len(hosts_result)} shadow hosts:")
            for host in hosts_result:
                print(
                    f"  - {host['tagName']} (class: {host['className']}, id: {host['id']})"
                )
        except Exception as e:
            print(f"Error in findShadowHosts: {e}")

        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
