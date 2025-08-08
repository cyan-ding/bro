"""
@file purpose: Tests the iframe extraction JavaScript code in a web page context using Playwright.
This script is intended for testing the iframe extraction logic in a real browser environment.
"""

import asyncio
from patchright.async_api import async_playwright
from pathlib import Path


async def main() -> None:
    """
    Launches a Chromium browser, navigates to a target page, injects the iframe extraction JS code,
    and calls the iframe extraction functions.
    """
    # Read the iframe extraction script
    iframe_extraction_path = Path(__file__).parent / "extract_iframes_best.js"
    iframe_extraction_code = iframe_extraction_path.read_text(encoding="utf-8")

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
                # Test pages with iframes
                "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe",  # MDN iframe docs
                # "https://www.w3schools.com/html/html_iframe.asp",  # W3Schools iframe tutorial
                # "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3024.2219901290355!2d-74.00369368400567!3d40.71312937933185!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x89c25a23e28c1191%3A0x49f75d3281df052a!2s150%20Park%20Row%2C%20New%20York%2C%20NY%2010007!5e0!3m2!1sen!2sus!4v1640995200000!5m2!1sen!2sus",  # Google Maps embed
                wait_until="domcontentloaded",
            )
        except Exception as e:
            print("Browser timed out:", e)
            await browser.close()
            return

        # Inject the iframe extraction script
        await page.evaluate(iframe_extraction_code)

        # Test basic iframe finding
        print("Testing basic iframe finding:")
        try:
            iframes_result = await page.evaluate("() => window.findIframes()")
            print(f"findIframes found {len(iframes_result)} iframes:")
            for iframe in iframes_result:
                print(
                    f"  - {iframe['tagName']} (class: {iframe['className']}, id: {iframe['id']}, src: {iframe['src']})"
                )
        except Exception as e:
            print(f"Error in findIframes: {e}")

        # Test detailed iframe extraction
        print("\nTesting detailed iframe extraction:")
        try:
            detailed_result = await page.evaluate("() => window.findIframesDetailed()")
            print(f"findIframesDetailed found {len(detailed_result)} iframes:")
            for iframe in detailed_result:
                print(
                    f"  - {iframe['tagName']} (id: {iframe['id']}, src: {iframe['src']})"
                )
                if iframe["iframeContent"]:
                    if iframe["iframeContent"].get("error"):
                        print(
                            f"    Error accessing content: {iframe['iframeContent']['error']}"
                        )
                    else:
                        print(
                            f"    Title: {iframe['iframeContent'].get('title', 'N/A')}"
                        )
                        print(f"    URL: {iframe['iframeContent'].get('url', 'N/A')}")
                        print(
                            f"    Content length: {len(iframe['iframeContent'].get('bodyHTML', ''))}"
                        )
        except Exception as e:
            print(f"Error in findIframesDetailed: {e}")

        # Test iframe summary extraction
        print("\nTesting iframe summary extraction:")
        try:
            summary_result = await page.evaluate(
                "() => window.extractIframesBestSummary()"
            )
            print(f"Total iframes found: {summary_result['totalIframes']}")
            if summary_result["summary"]:
                print("Iframe elements found:")
                for iframe in summary_result["summary"]:
                    print(
                        f"  - {iframe['hostTag']} (class: {iframe['hostClass']}, id: {iframe['hostId']}, src: {iframe['src']})"
                    )
                    print(
                        f"    Accessible: {iframe['accessible']}, Has content: {iframe['hasContent']}, Content length: {iframe['contentLength']}"
                    )
            else:
                print("No iframe elements found on this page")
        except Exception as e:
            print(f"Error in extractIframesBestSummary: {e}")

        # Test iframe content extraction
        print("\nTesting iframe content extraction:")
        try:
            content_result = await page.evaluate("() => window.extractIframeContent()")
            print(f"Total iframes: {content_result['totalIframes']}")
            print(f"Accessible iframes: {content_result['accessibleIframes']}")
            for result in content_result["contentResults"]:
                print(
                    f"  - Iframe {result['index']}: {result['tagName']} (id: {result['id']}, src: {result['src']})"
                )
                print(f"    Accessible: {result['accessible']}")
                if result["error"]:
                    print(f"    Error: {result['error']}")
                elif result["content"]:
                    print(f"    Title: {result['content'].get('title', 'N/A')}")
                    print(
                        f"    Content length: {len(result['content'].get('bodyHTML', ''))}"
                    )
        except Exception as e:
            print(f"Error in extractIframeContent: {e}")

        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
