"""
DOM and element utilities for Bro web interaction agent.

This module contains functions for DOM analysis, element highlighting,
screenshot capture, and element description formatting.

@file purpose: Provides DOM analysis and element utilities for Bro
"""

import asyncio
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from patchright.async_api import Page, async_playwright


async def load_js_bundle() -> str:
    """Load and bundle the JavaScript code for DOM analysis with caching."""
    base_path = Path(__file__).parent.parent / "dom"
    cache_file = base_path / "js_bundle_cache.txt"
    files_in_order = [
        "metrics.js",
        "highlight.js",
        "dom_utils.js",
        "buildDomTree.js",
    ]

    # Always rebuild the bundle to ensure latest JS changes are injected
    # If you need caching for performance, implement a content hash/versioned cache.
    if cache_file.exists():
        try:
            _ = cache_file.read_text(encoding="utf-8")
        except (OSError, IOError) as e:
            print(f"Error reading cache file: {e}")
        # Proceed to rebuild regardless

    # Rebuild the bundle
    full_code = []
    for file_name in files_in_order:
        file_path = base_path / file_name
        try:
            code = file_path.read_text(encoding="utf-8")
            # Remove import/export statements
            code = re.sub(r"^\s*import .*from .*", "", code, flags=re.MULTILINE)
            code = re.sub(r"^\s*export (default )?", "", code, flags=re.MULTILINE)
            full_code.append(code)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error loading JavaScript file {file_name}: {e}")
            raise RuntimeError(f"Failed to load required JavaScript file: {file_name}")

    # Wrap in an IIFE to expose the main function
    bundle = f"""
    (() => {{
        {"".join(full_code)}
        window.buildDomTree = buildDomTree;
    }})();
    """

    # Cache the bundle
    try:
        cache_file.write_text(bundle, encoding="utf-8")
    except (OSError, IOError) as e:
        print(f"Warning: Could not write cache file: {e}")

    return bundle


def _compute_highlight_signature(highlighted_elements: List[Dict[str, Any]]) -> str:
    """Compute a stable signature for a list of highlighted elements.

    The signature intentionally ignores volatile fields like element indices and
    bounding rectangles. It focuses on relatively stable identifiers to detect
    meaningful DOM/state transitions between iterations (e.g., Google auth steps).

    Args:
        highlighted_elements: The list of highlighted element dicts returned by buildDomTree

    Returns:
        Hex-encoded SHA-256 signature string
    """
    stable_fingerprints: List[str] = []
    for element in highlighted_elements or []:
        tag = element.get("tag", "")
        xpath = element.get("xpath", "")
        info = element.get("info", {}) or {}
        # Include a minimal set of relatively stable attributes
        placeholder = info.get("placeholder", "")
        role = info.get("role", "")
        aria_label = info.get("ariaLabel", "")
        input_type = info.get("type", "")
        text = (info.get("textContent", "") or "")[:64]
        stable_fingerprints.append(
            f"{tag}|{xpath}|{placeholder}|{role}|{aria_label}|{input_type}|{text}"
        )

    stable_fingerprints.sort()
    payload = json.dumps(stable_fingerprints, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def wait_for_navigation(page: Page, timeout_ms: int) -> Dict[str, Any]:
    """Wait for navigation using expect_navigation pattern.

    Args:
        page: The Playwright page object
        timeout_ms: Maximum time to wait in milliseconds

    Returns:
        Dict with navigation result info
    """

    # After navigation completes, ensure DOM is ready and compute fresh values
    try:
        async with page.expect_navigation(timeout=timeout_ms):
            await asyncio.sleep(timeout_ms / 1000)  # prevent immediate exit

        await page.wait_for_load_state("domcontentloaded")
    except Exception as e:
        print("error: ", e)
        pass

    # Ensure JS bundle is available
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    # Get fresh DOM state after navigation
    build_args = {
        "doHighlightElements": True,
        "debugMode": False,
        "overlapThreshold": 0.7,
        "indexByPosition": True,
    }

    result = await page.evaluate(
        "(args) => window.buildDomTree(args)",
        build_args,
    )
    highlighted_elements = result.get("highlightedElements", [])
    signature = _compute_highlight_signature(highlighted_elements)
    return {
        "type": "navigation",
        "signature": signature,
        "highlighted_elements": highlighted_elements,
    }


async def poll_dom(
    page: Page,
    previous_signature: str,
    timeout_ms: int,
    poll_interval_ms: int = 100,
    stabilize_after_change_ms: int = 400,
) -> Dict[str, Any]:
    """Poll DOM for changes until a change is detected or timeout.

    Args:
        page: The Playwright page object
        previous_signature: The signature to compare against
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: Polling interval in milliseconds
        stabilize_after_change_ms: Time to wait after change for stabilization

    Returns:
        Dict with DOM change result info
    """
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)

    # Ensure JS bundle is available for polling
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    build_args = {
        "doHighlightElements": True,
        "debugMode": False,
        "overlapThreshold": 0.7,
        "indexByPosition": True,
    }

    async def _get_highlight_and_signature() -> Tuple[List[Dict[str, Any]], str]:
        """Rebuild DOM tree and compute highlighted elements and signature."""
        result_local = await page.evaluate(
            "(args) => window.buildDomTree(args)",
            build_args,
        )
        highlighted_local = result_local.get("highlightedElements", [])
        signature_local = _compute_highlight_signature(highlighted_local)
        return highlighted_local, signature_local

    latest_signature: Optional[str] = None
    latest_highlighted: List[Dict[str, Any]] = []

    while True:
        # Poll DOM by rebuilding
        latest_highlighted, latest_signature = await _get_highlight_and_signature()

        if latest_signature != previous_signature:
            # Detected a real change; linger briefly to allow UI to stabilize
            stabilization_deadline = min(
                asyncio.get_running_loop().time()
                + (stabilize_after_change_ms / 1000.0),
                deadline,
            )
            last_signature = latest_signature

            # Continue polling until we observe a quiet period or hit deadlines
            while True:
                now = asyncio.get_running_loop().time()
                if now >= stabilization_deadline or now >= deadline:
                    return {
                        "type": "dom_change",
                        "signature": latest_signature,
                        "highlighted_elements": latest_highlighted,
                    }

                await asyncio.sleep(poll_interval_ms / 1000.0)
                # Track most recent observation to return
                (
                    latest_highlighted,
                    current_signature,
                ) = await _get_highlight_and_signature()
                latest_signature = current_signature

                # If signature changed again, extend the stabilization window
                if current_signature != last_signature:
                    last_signature = current_signature
                    stabilization_deadline = min(
                        asyncio.get_running_loop().time()
                        + (stabilize_after_change_ms / 1000.0),
                        deadline,
                    )

        # Timeout check
        if asyncio.get_running_loop().time() >= deadline:
            return {
                "type": "timeout",
                "signature": latest_signature,
                "highlighted_elements": latest_highlighted,
            }

        await asyncio.sleep(poll_interval_ms / 1000.0)


async def _wait_for_dom_change_or_navigation(
    page: Page,
    previous_signature: Optional[str],
    timeout_ms: int = 1500,
    poll_interval_ms: int = 100,
    stabilize_after_change_ms: int = 400,
) -> Dict[str, Any]:
    """Wait for either a navigation or a detectable DOM change via highlighted elements.

    Args:
        page: The Playwright page object
        previous_signature: The prior signature to compare against. If None, returns immediately
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: Polling interval in milliseconds
        stabilize_after_change_ms: After detecting the first real DOM change, keep
            waiting up to this additional duration (reset if further changes occur)
            so the UI can settle before returning.

    Returns:
        Dict with keys:
            - signature: latest observed or changed signature
            - highlighted_elements: latest observed list of highlighted elements
    """
    # If there's no prior signature, nothing to compare; return immediately.
    if not previous_signature:
        return {"signature": None, "highlighted_elements": []}

    # Create tasks for navigation and DOM polling
    nav_task = asyncio.create_task(wait_for_navigation(page, timeout_ms))
    dom_task = asyncio.create_task(
        poll_dom(
            page,
            previous_signature,
            timeout_ms,
            poll_interval_ms,
            stabilize_after_change_ms,
        )
    )

    try:
        # Race condition: wait for first to complete
        done, pending = await asyncio.wait(
            {nav_task, dom_task}, return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks (fix: remove await)
        for task in pending:
            task.cancel()

        # Get result from completed task
        for task in done:
            result = await task
            print(
                "wait_for_dom_change_or_navigation: ",
                result.get("highlighted_elements", []),
            )

            return {
                "type": result.get("type"),
                "signature": result.get("signature"),
                "highlighted_elements": result.get("highlighted_elements", []),
            }

    except Exception as e:
        # Clean up tasks on exception (fix: remove await)
        nav_task.cancel()
        dom_task.cancel()
        # Return empty result on error
        print("error: ", e)
        return {"signature": None, "highlighted_elements": []}


async def take_screenshot_with_bounding_boxes(
    page: Page,
    wait_for_change: bool = False,
    previous_signature: Optional[str] = None,
    timeout_ms: int = 1500,
    poll_interval_ms: int = 100,
) -> Optional[Dict[str, Any]]:
    """
    Take a screenshot and analyze the DOM to get bounding boxes and element information.

    Optionally waits for either a navigation or a detected DOM change compared to a
    provided previous signature, which helps synchronize with SPA updates.

    Args:
        page: The Playwright page object
        wait_for_change: Whether to wait for a DOM change or navigation before capturing
        previous_signature: The previous signature to compare against when wait_for_change is True
        timeout_ms: Max wait duration for change/navigation
        poll_interval_ms: Polling interval when waiting for change

    Returns:
        Dictionary containing screenshot data, highlighted elements, viewport info, and signature
    """
    if page.url == "about:blank":
        return None

    # Ensure document is at least DOMContentLoaded once
    await page.wait_for_load_state("domcontentloaded")

    # If requested, wait until either navigation or a genuine DOM change occurs
    if wait_for_change:
        try:
            change_result = await _wait_for_dom_change_or_navigation(
                page,
                previous_signature=previous_signature,
                timeout_ms=timeout_ms,
                poll_interval_ms=poll_interval_ms,
            )
            # If we detected a change (different signature)
            cached_signature = change_result.get("signature")
        except Exception:
            # Best-effort wait; proceed even if waiting throws
            cached_signature = None

    print("Walking DOM Tree...")
    # Load the JavaScript bundle
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    # Always call buildDomTree to obtain current raw and serialized highlights
    result = await page.evaluate(
        "(args) => window.buildDomTree(args)",
        {
            "doHighlightElements": True,
            "debugMode": False,
            "overlapThreshold": 0.7,
            "indexByPosition": True,
        },
    )

    print("Highlighted Elements: ", result.get("highlightedElements"))

    # Get viewport information for smart scrolling
    viewport_info = await page.evaluate("""
        () => {
            const scrollY = window.scrollY;
            const innerHeight = window.innerHeight;
            const documentHeight = document.documentElement.scrollHeight;
            return {
                innerHeight: innerHeight,
                documentHeight: documentHeight,
                pixelsAbove: scrollY,
                pixelsBelow: documentHeight - (scrollY + innerHeight)
            };
        }
    """)
    # Take screenshot
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Compute and return a stable signature for next-iteration comparisons (based on raw highlights)
    signature = (
        cached_signature
        if wait_for_change and cached_signature
        else _compute_highlight_signature(result.get("highlightedElements", []))
    )

    return {
        "screenshot": screenshot_base64,
        # Use serialized highlights for downstream formatting and actions
        "highlighted_elements": result.get("highlightedElementsSerialized", []),
        # Keep raw highlights for diagnostics/signature if needed
        "highlighted_elements_raw": result.get("highlightedElements", []),
        "viewport_info": viewport_info,
        "signature": signature,
    }


async def test_dom_polling_vs_direct_injection(
    page: Page,
    timeout_ms: int = 1500,
    poll_interval_ms: int = 100,
) -> Dict[str, Any]:
    """
    Test function to compare DOM polling behavior vs direct buildDomTree injection.

    This function captures both approaches and returns their results for comparison,
    helping determine if the continuous polling provides different results than
    direct injection.

    Args:
        page: The Playwright page object
        timeout_ms: Maximum wait time for polling approach
        poll_interval_ms: Polling interval for DOM change detection

    Returns:
        Dictionary containing results from both approaches and comparison metrics
    """
    if page.url == "about:blank":
        return {"error": "Cannot test on blank page"}

    build_args = {
        "doHighlightElements": True,
        "debugMode": False,
        "overlapThreshold": 0.7,
        "indexByPosition": True,
    }

    # Approach 1: Direct injection (current final step in take_screenshot_with_bounding_boxes)
    print("Testing direct injection approach...")
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    direct_result = await page.evaluate(
        "(args) => window.buildDomTree(args)",
        build_args,
    )
    direct_signature = _compute_highlight_signature(
        direct_result.get("highlightedElements", [])
    )
    print("direct_result: ", direct_result.get("highlightedElements", []))
    await page.screenshot(path="direct_injection.png")
    # Approach 2: DOM polling approach (what _wait_for_dom_change_or_navigation does)
    print("Testing DOM polling approach...")
    polling_result = None
    polling_signature = None

    try:
        # Use a fake previous signature to force polling to timeout and return current state
        fake_previous_signature = "fake_signature_for_testing"
        change_result = await _wait_for_dom_change_or_navigation(
            page,
            previous_signature=fake_previous_signature,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )
        polling_signature = change_result.get("signature")
        polling_result = change_result.get("highlighted_elements", [])
        await page.screenshot(path="polling.png")
    except Exception as e:
        polling_result = [{"error": str(e)}]
        polling_signature = None

    # Compare results
    signatures_match = direct_signature == polling_signature
    element_counts_match = (
        len(direct_result.get("highlightedElements", [])) == len(polling_result)
        if polling_result
        else False
    )

    return {
        "direct_injection": {
            "signature": direct_signature,
            "element_count": len(direct_result.get("highlightedElements", [])),
        },
        "dom_polling": {
            "signature": polling_signature,
            "element_count": len(polling_result) if polling_result else 0,
        },
        "comparison": {
            "signatures_match": signatures_match,
            "element_counts_match": element_counts_match,
            "approaches_differ": not (signatures_match and element_counts_match),
        },
        "test_config": {
            "timeout_ms": timeout_ms,
            "poll_interval_ms": poll_interval_ms,
            "page_url": page.url,
        },
    }


async def main() -> None:
    # Launch Chrome with CDP port
    import subprocess
    import urllib.error
    import urllib.request

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

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # List contexts (Chrome profiles)
        contexts = browser.contexts
        if contexts:
            context = contexts[0]  # Use existing profile
        else:
            context = await browser.new_context()  # Or create new
        print(context.pages[0].url)
        # Open a new tab
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(
            # google form test
            # "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform",
            # google doc test
            # "https://docs.google.com/document/d/1DBPuFb-byQ9rZcxZo2ky0y5Sn1TjeF-2q6rfwOhI1sg/edit?usp=sharing",
            # google sheets test
            # "https://docs.google.com/spreadsheets/d/1seBguBzuDMYo6-7vZCOlb-Y6zFKTKKUYqJu81qxev6Q/edit?usp=sharing",
            # iframe test
            # "https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe",
            # sticky element test
            "https://en.wikipedia.org/wiki/English_Wikipedia",
            wait_until="domcontentloaded",
        )

        result = await test_dom_polling_vs_direct_injection(
            page,
            timeout_ms=1500,
            poll_interval_ms=100,
        )
        print(result)

        await page.wait_for_timeout(5000)
        await browser.close()  # Closes connection, not Chrome itself


if __name__ == "__main__":
    asyncio.run(main())
