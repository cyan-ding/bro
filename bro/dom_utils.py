"""
DOM and element utilities for Bro web interaction agent.

This module contains functions for DOM analysis, element highlighting,
screenshot capture, and element description formatting.

@file purpose: Provides DOM analysis and element utilities for Bro
"""

import base64
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from patchright.async_api import Page


async def load_js_bundle() -> str:
    """Load and bundle the JavaScript code for DOM analysis with caching."""
    base_path = Path(__file__).parent / "dom"
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


async def take_screenshot_with_bounding_boxes(page: Page) -> Optional[Dict[str, Any]]:
    """
    Take a screenshot and analyze the DOM to get bounding boxes and element information.

    Args:
        page: The Playwright page object

    Returns:
        Dictionary containing screenshot data and highlighted elements
    """
    if page.url == "about:blank":
        return None
    print("Walking DOM Tree...")
    # Load the JavaScript bundle
    js_bundle = await load_js_bundle()
    await page.evaluate(js_bundle)

    # Call buildDomTree to get element information and highlighting
    result = await page.evaluate(
        "(args) => window.buildDomTree(args)",
        {
            "doHighlightElements": True,
            "debugMode": False,
            "overlapThreshold": 0.4,
            "indexByPosition": True,
        },
    )

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
    print("Highlighted elements: ", result.get("highlightedElements", []))
    # Take screenshot
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    return {
        "screenshot": screenshot_base64,
        "highlighted_elements": result.get("highlightedElements", []),
        "viewport_info": viewport_info,
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
