"""
Action utilities for Bro web interaction agent.

This module contains functions for handling previous actions
and generating descriptive action text.

@file purpose: Provides action utilities for Bro
"""

from typing import Any, Dict, List, Optional


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


def generate_action_description(
    action_name: str,
    arguments: Dict[str, Any],
    highlighted_elements: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate a human-readable description of an action with optional element context.

    Args:
        action_name: Name of the action
        arguments: Arguments passed to the action
        highlighted_elements: Optional list of highlighted elements for detailed descriptions

    Returns:
        Human-readable description of the action
    """

    def _get_element_desc(index):
        """Helper to get element description with fallback."""
        if highlighted_elements and get_element_description:
            return get_element_description(index, highlighted_elements)
        return f"element at index {index}"

    if action_name == "click":
        target = arguments.get("target", "unknown")
        element_desc = _get_element_desc(target)
        return f"You clicked on {element_desc}"
    elif action_name == "input_text":
        target = arguments.get("target", "unknown")
        element_desc = _get_element_desc(target)
        text = arguments.get("input_text", "")
        return f"You typed '{text}' into {element_desc}"
    elif action_name == "scroll":
        how_much = arguments.get("how_much", "")
        return f"You scrolled by {how_much} pixels"
    elif action_name == "search":
        query = arguments.get("query", "")
        tab_index = arguments.get("tab_index")
        if tab_index is not None:
            return f"You switched to tab {tab_index}"
        else:
            return f"You searched for '{query}'"
    elif action_name == "extract":
        return "You extracted the page content and converted it to markdown"
    elif action_name == "todo_edit":
        todo_items = arguments.get("todo_items", [])
        num_items = len(todo_items)
        completed_count = sum(1 for item in todo_items if item.get("completed", False))
        return f"You updated the todo list with {num_items} items ({completed_count} completed)"
    elif action_name == "done":
        reason = arguments.get("reason", "task completed")
        return f"You marked the task as done with reason: '{reason}'"
    else:
        return f"You executed '{action_name}'"
