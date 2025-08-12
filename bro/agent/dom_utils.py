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
from typing import Any, Dict, List, Optional

from patchright.async_api import Page


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

    # Check if cache exists and use it
    if cache_file.exists():
        try:
            cached_bundle = cache_file.read_text(encoding="utf-8")
            return cached_bundle
        except (OSError, IOError) as e:
            print(f"Error reading cache file: {e}")
            # Continue to rebuild if cache read fails

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


async def _wait_for_dom_change_or_navigation(
    page: Page,
    previous_signature: Optional[str],
    timeout_ms: int = 1500,
    poll_interval_ms: int = 100,
) -> Dict[str, Any]:
    """Wait for either a navigation or a detectable DOM change via highlighted elements.

    Args:
        page: The Playwright page object
        previous_signature: The prior signature to compare against. If None, returns immediately
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: Polling interval in milliseconds

    Returns:
        Dict with keys:
            - signature: latest observed or changed signature
            - highlighted_elements: latest observed list of highlighted elements
    """
    # If there's no prior signature, nothing to compare; return immediately.
    if not previous_signature:
        return {"signature": None, "highlighted_elements": []}

    # Start a short navigation wait in parallel. It will resolve only if a real navigation occurs.
    nav_task = asyncio.create_task(page.wait_for_navigation(timeout=timeout_ms))

    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)
    latest_signature: Optional[str] = None
    latest_highlighted: List[Dict[str, Any]] = []

    # Ensure JS bundle is available for polling
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    while True:
        # If navigation completed, wait for DOM to be ready once and compute new signature
        if nav_task.done():
            try:
                # Ensure the navigated document is at least DOMContentLoaded
                await page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass
            # One fresh build and signature
            result_after_nav = await page.evaluate(
                "(args) => window.buildDomTree(args)",
                {
                    "doHighlightElements": True,
                    "debugMode": False,
                    "overlapThreshold": 0.7,
                    "indexByPosition": True,
                },
            )
            latest_highlighted = result_after_nav.get("highlightedElements", [])
            latest_signature = _compute_highlight_signature(latest_highlighted)
            return {
                "signature": latest_signature,
                "highlighted_elements": latest_highlighted,
            }

        # Poll DOM by rebuilding
        result = await page.evaluate(
            "(args) => window.buildDomTree(args)",
            {
                "doHighlightElements": True,
                "debugMode": False,
                "overlapThreshold": 0.7,
                "indexByPosition": True,
            },
        )
        current_highlighted = result.get("highlightedElements", [])
        latest_highlighted = current_highlighted
        latest_signature = _compute_highlight_signature(current_highlighted)

        if latest_signature != previous_signature:
            # Detected a real change; stop waiting for nav and proceed
            if not nav_task.done():
                try:
                    nav_task.cancel()
                except Exception:
                    pass
            return {
                "signature": latest_signature,
                "highlighted_elements": latest_highlighted,
            }

        # Timeout check
        if asyncio.get_running_loop().time() >= deadline:
            return {
                "signature": latest_signature,
                "highlighted_elements": latest_highlighted,
            }

        await asyncio.sleep(poll_interval_ms / 1000.0)


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
            # If we detected a change (different signature), we can use these highlighted elements
            cached_highlighted_elements = change_result.get("highlighted_elements", [])
            cached_signature = change_result.get("signature")
        except Exception:
            # Best-effort wait; proceed even if waiting throws
            cached_highlighted_elements = []
            cached_signature = None

    print("Walking DOM Tree...")
    # Load the JavaScript bundle
    domTreeInjected = await page.evaluate("window.domTreeInjected")
    if not domTreeInjected:
        js_bundle = await load_js_bundle()
        await page.evaluate(js_bundle)

    # If we have cached highlighted elements from a detected change, reuse them to avoid another call
    if wait_for_change and cached_highlighted_elements:
        result = {"highlightedElements": cached_highlighted_elements}
    else:
        # Call buildDomTree to get element information and highlighting
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

    # Compute and return a stable signature for next-iteration comparisons
    signature = (
        cached_signature
        if wait_for_change and cached_signature
        else _compute_highlight_signature(result.get("highlightedElements", []))
    )

    return {
        "screenshot": screenshot_base64,
        "highlighted_elements": result.get("highlightedElements", []),
        "viewport_info": viewport_info,
        "signature": signature,
    }


async def format_elements_text(highlighted_elements: List[Dict]) -> str:
    """
    Format the highlighted elements into readable text for the LLM.

    Args:
        highlighted_elements: List of highlighted element data

    Returns:
        Formatted text describing all interactive elements
    """
    if not highlighted_elements:
        return "No interactive elements found on the page."
    print("Formatting elements...")
    elements_text = "Interactive elements on the page:\n\n"
    for i, element in enumerate(highlighted_elements):
        elements_text += f"Index {i}: {element.get('tag', 'unknown')}"
        if element.get("info", {}).get("textContent"):
            elements_text += f" - '{element['info']['textContent']}'"
        if element.get("info", {}).get("href"):
            elements_text += f" (href: {element['info']['href']})"
        if element.get("info", {}).get("placeholder"):
            elements_text += f" (placeholder: {element['info']['placeholder']})"
        elements_text += "\n"

    return elements_text


def get_element_description(index: int, highlighted_elements: List[Dict]) -> str:
    """
    Get a descriptive string for an element at the given index.

    Args:
        index: The index of the element
        highlighted_elements: List of highlighted element data

    Returns:
        Descriptive string for the element
    """
    if not highlighted_elements or index >= len(highlighted_elements):
        return f"element at index {index}"

    element = highlighted_elements[index]
    tag = element.get("tag", "unknown")
    info = element.get("info", {})

    description_parts = [tag]

    if info.get("textContent"):
        description_parts.append(f"'{info['textContent']}'")
    if info.get("placeholder"):
        description_parts.append(f"placeholder '{info['placeholder']}'")
    if info.get("href"):
        description_parts.append(f"link to {info['href']}")

    return " ".join(description_parts)
