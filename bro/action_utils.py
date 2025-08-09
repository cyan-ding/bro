"""
Action utilities for Bro web interaction agent.

This module contains functions for handling previous actions
and generating descriptive action text.

@file purpose: Provides action utilities for Bro
"""

from typing import Dict, List

from .dom_utils import get_element_description


def get_previous_action_description(
    previous_action: Dict, previous_elements: List[Dict]
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
    if action_name == "click" and "index" in action_args:
        element_desc = get_element_description(action_args["index"], previous_elements)
        desc = f"You clicked on {element_desc} in the last iteration."
    elif action_name == "type" and "index" in action_args:
        element_desc = get_element_description(action_args["index"], previous_elements)
        text_entered = action_args.get("text", "")
        desc = f"You typed '{text_entered}' into {element_desc} in the last iteration."
    elif action_name == "scroll":
        direction = action_args.get("direction", "unknown")
        desc = f"You scrolled {direction} in the last iteration."
    elif action_name == "done":
        reason = action_args.get("reason", "task completed")
        desc = f"You marked the task as done with reason: '{reason}' in the last iteration."
    else:
        args_str = f" with arguments: {action_args}" if action_args else ""
        desc = f"You executed '{action_name}{args_str}' in the last iteration."
    return template.format(desc=desc)
