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


def get_previous_action_description(
    previous_action: Dict[str, Any], previous_elements: List[Dict[str, Any]]
) -> str:
    """
    Get a descriptive string for the previous action.

    Args:
        previous_action: Dictionary containing action name and arguments
        previous_elements: List of highlighted element data from previous iteration

    Returns:
        Descriptive string for the previous action
    """
    if not previous_action or not previous_elements:
        return ""

    action_name = previous_action.get("name", "unknown")
    action_args = previous_action.get("arguments", {})
    # Use a template for the previous action message
    template = "\nPrevious action: {desc} Please follow up on this action."

    # Create descriptive action text
    if action_name == "click" and "target" in action_args:
        idx = action_args.get("target")
        element_desc = get_element_description(idx, previous_elements)
        desc = f"You clicked on {element_desc} in the last iteration."
    elif action_name == "input_text" and "target" in action_args:
        idx = action_args.get("target")
        element_desc = get_element_description(idx, previous_elements)
        text_entered = action_args.get("input_text", "")
        login = action_args.get("login", "")
        if login:
            retry_login = action_args.get("retry_login", False)
            if retry_login:
                desc = f"You tried and failed to log in with '{login}' into {element_desc} in the last iteration."
            else:
                desc = f"You tried to log in with '{login}' into {element_desc} in the last iteration."
        else:
            desc = (
                f"You typed '{text_entered}' into {element_desc} in the last iteration."
            )
    elif action_name == "scroll":
        how_much = action_args.get("how_much", "")
        desc = f"You scrolled by {how_much} pixels in the last iteration."
    elif action_name == "done":
        reason = action_args.get("reason", "task completed")
        desc = f"You marked the task as done with reason: '{reason}' in the last iteration."
    else:
        args_str = f" with arguments: {action_args}" if action_args else ""
        desc = f"You executed '{action_name}{args_str}' in the last iteration."
    return template.format(desc=desc)


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
