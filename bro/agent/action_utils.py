"""
Action utilities for Bro web interaction agent.

This module contains functions for handling previous actions
and generating descriptive action text.

@file purpose: Provides action utilities for Bro
"""

from typing import Any, Dict, List


def get_element_description(
    index: int, highlighted_elements: List[Dict[str, Any]]
) -> str:
    """
    Render a single-line inspiration-style description for the element at index.

    Args:
        index: Highlight index of the element to describe
        highlighted_elements: Serialized highlighted elements from JS

    Returns:
        A single formatted line, e.g., "[7]<a href=/settings >Settings />"
    """
    if not highlighted_elements:
        return f"element at index {index}"

    # Find by stable highlight index
    el: Dict[str, Any] = next(
        (
            e
            for e in highlighted_elements
            if isinstance(e, dict) and e.get("index") == index
        ),
        None,
    )  # type: ignore
    if not el:
        # Fallback: position-based
        if index < len(highlighted_elements):
            el = highlighted_elements[index]  # type: ignore
        else:
            return f"element at index {index}"

    tag = el.get("tag", "unknown")
    depth = int(el.get("depth", 0) or 0)
    is_new = bool(el.get("isNew", False))
    attrs: Dict[str, Any] = el.get("attrs", {}) or {}
    text = (el.get("text") or "").strip()

    indent = "\t" * depth
    marker = f"*[{index}]" if is_new else f"[{index}]"

    # Build attribute string from pruned attrs
    attr_parts: List[str] = []
    for k, v in attrs.items():
        if v is None or v == "":
            continue
        attr_parts.append(f"{k}={v}")
    attrs_str = " ".join(attr_parts)

    line = f"{indent}{marker}<{tag}"
    if attrs_str:
        line += f" {attrs_str}"
    if text:
        if not attrs_str:
            line += " "
        line += f">{text}"
    elif not attrs_str:
        line += " "
    line += " />"
    return line

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
    lines: List[str] = []

    # Keep provided order; they are already sorted by highlightIndex
    for el in highlighted_elements:
        if isinstance(el, dict) and "index" in el:
            lines.append(get_element_description(el["index"], highlighted_elements))

    return "\n".join(lines)
