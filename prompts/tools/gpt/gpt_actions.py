"""
GPT Actions Prompt Function

This module provides a prompt function for GPT that includes all available action tools
for interacting with web pages.

@file purpose: Provides GPT prompt function with action tools for web interaction
"""

from typing import Optional


def gpt_actions(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-5-nano-2025-08-07",
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
    query = [
        {"role": "system", "content": system_prompt},
    ]

    # Add screenshot if provided
    if screenshot:
        query.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot}",
                    },
                    {"type": "input_text", "text": user_prompt},
                ],
            }
        )
    else:
        query.append({"role": "user", "content": user_prompt})

    return {
        "model": model,
        "input": query,
        "reasoning": {
            "effort": "medium",
            "summary": "auto",
        },
        "tools": [
            {
                "type": "function",
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
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "input_text",
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
                            "type": "string",
                            "description": "Optional login credential type (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD')",
                        },
                        "retry_login": {
                            "type": "boolean",
                            "description": "Set to true if the web page shows an error message about incorrect credentials.",
                        },
                    },
                    "required": ["target", "input_text"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
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
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "search",
                "description": "Search Google for a query and navigate to results. Use this to navigate to any website. Do not input direct URLs into this tool - only search queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to perform on Google (e.g., 'google accounts login', 'facebook login', 'amazon.com', etc.)",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            # {
            #     "type": "function",
            #     "name": "extract",
            #     "description": "Extract and return the main text content from the current page using Trafilatura",
            #     "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            #     "strict": True,
            # },
            {
                "type": "function",
                "name": "done",
                "description": "Signal that the user's task is completed or that the agent is unable to proceed. This will stop the agent execution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Reason for completion or stopping (e.g., 'Task completed successfully', 'Unable to proceed due to missing credentials', 'No interactive elements found')",
                        },
                    },
                    "required": ["reason"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            # {
            #     "type": "function",
            #     "name": "write_file",
            #     "description": "Update the current session's todo list with new content. This will replace the entire content of the todo.md file for this session. This function should be called after each step to mark off what subtasks have been completed and update what subtasks have yet to be done.",
            #     "parameters": {
            #         "type": "object",
            #         "properties": {
            #             "content": {
            #                 "type": "string",
            #                 "description": "The new content to write to the todo.md file. This should contain the updated todo list with boxes checked off if completed.",
            #             },
            #         },
            #         "required": ["content"],
            #         "additionalProperties": False,
            #     },
            #     "strict": True,
            # },
            # {
            #     "type": "function",
            #     "name": "read_file",
            #     "description": "Read the current session's todo list to understand the current progress and remaining tasks. Use this to check what has been completed and what still needs to be done.",
            #     "parameters": {
            #         "type": "object",
            #         "properties": {},
            #         "required": [],
            #         "additionalProperties": False,
            #     },
            #     "strict": True,
            # },
        ],
        "tool_choice": "required",
    }
