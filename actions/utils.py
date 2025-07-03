"""
This file provides utility functions for browser actions in Bro.
It includes selector generation logic for Playwright elements, to support robust workflow serialization.

# @file purpose: Defines utility functions for browser actions, including selector generation for workflow steps.
"""

from patchright.async_api import ElementHandle


async def get_best_selector(element: ElementHandle) -> str:
    """
    Generate a robust selector for a Playwright element.
    Tries id, name, aria-label, placeholder, data-testid, type+class, text for buttons/links, then tag+class.
    Returns a CSS selector string.
    """
    # Try id
    el_id = await element.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    # Try name
    name = await element.get_attribute("name")
    if name:
        return f"[name='{name}']"
    # Try aria-label
    aria_label = await element.get_attribute("aria-label")
    if aria_label:
        return f"[aria-label='{aria_label}']"
    # Try placeholder
    placeholder = await element.get_attribute("placeholder")
    if placeholder:
        return f"[placeholder='{placeholder}']"
    # Try data-testid
    data_testid = await element.get_attribute("data-testid")
    if data_testid:
        return f"[data-testid='{data_testid}']"
    # Try type + class
    el_type = await element.get_attribute("type")
    el_class = await element.get_attribute("class")
    if el_type and el_class:
        first_class = el_class.split()[0]
        return f"[type='{el_type}'][class*='{first_class}']"
    # Try text content for buttons/links
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    if tag in ["button", "a"]:
        text = await element.inner_text()
        if text and len(text.strip()) < 40:
            safe_text = text.strip().replace("'", "\\'")
            return f"{tag}:has-text('{safe_text}')"
    # Fallback: tag + first class
    if el_class:
        first_class = el_class.split()[0]
        return f"{tag}.{first_class}"
    # Last resort: just tag
    return tag
