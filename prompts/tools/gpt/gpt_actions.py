"""
GPT Actions Prompt Function

This module provides a prompt function for GPT that includes all available action tools
for interacting with web pages. The LLM is instructed to choose one tool call at a time
based on bounding box indices provided with screenshots.

@file purpose: Provides GPT prompt function with action tools for web interaction
"""

from typing import Optional


def gpt_actions(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-4o",
    screenshot: Optional[str] = None,
):
    """
    Creates a GPT prompt configuration with action tools for web interaction.

    Args:
        user_prompt: The user's input prompt describing the task
        system_prompt: The system prompt to guide the AI's behavior
        model: The GPT model to use (default: gpt-4o)
        screenshot: Optional base64 encoded screenshot to include in the prompt

    Returns:
        Dictionary containing the model configuration and tool definitions
    """
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Add screenshot if provided
    if screenshot:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot}"},
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_prompt})

    return {
        "model": model,
        "messages": messages,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click on an interactive element on the page using its index number",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "integer",
                                "description": "The index number of the element to click (e.g., 0, 1, 2, etc.)",
                            },
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "text_input",
                    "description": "Enter text into an input field on the page using multiple strategies (fill, type, keyboard)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "integer",
                                "description": "The index number of the input field (e.g., 0, 1, 2, etc.) as provided in the current page information",
                            },
                            "input_text": {
                                "type": "string",
                                "description": "The text to enter into the input field",
                            },
                            "login": {
                                "type": "object",
                                "description": "Optional login credentials object",
                                "properties": {
                                    "placeholder": {
                                        "type": "string",
                                        "description": "Placeholder for credential type (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD')",
                                    }
                                },
                                "required": ["placeholder"],
                            },
                        },
                        "required": ["target", "input_text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll",
                    "description": "Scroll the page up or down based on current viewport position",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "how_much": {
                                "type": "integer",
                                "description": "Number of pixels to scroll (positive for down, negative for up). Consider current viewport position when choosing amount.",
                            }
                        },
                        "required": ["how_much"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search Google for a query and navigate to results",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to perform on Google",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "extract",
                    "description": "Extract and return the main text content from the current page using Trafilatura",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ],
        "tool_choice": "auto",
    }
