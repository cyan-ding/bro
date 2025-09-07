from typing import Optional
import litellm


def build_llm_prompt(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-5-mini-2025-08-07",
    screenshot: Optional[str] = None,
):
    """
    Creates a LLM prompt configuration with action tools for web interaction.
    Uses LiteLLM's standardized chat completion format with reasoning support.

    Args:
        user_prompt: The user's input prompt describing the task
        system_prompt: The system prompt to guide the AI's behavior
        model: The LLM model to use (default: gpt-5-mini-2025-08-07)
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

    base_config = {
        "model": model,
        "messages": messages,
    }
    
    # Add reasoning effort if the model supports it
    if litellm.supports_reasoning(model=model):
        base_config["reasoning_effort"] = "medium"
    
    # Add tools configuration
    base_config.update({
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click on an interactive element on the page using its index number",
                    "strict": True,
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
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "input_text",
                    "description": """Enter text into an input field on the page using multiple strategies (fill, type, keyboard)""",
                    "strict": True,
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
                                "type": ["string", "null"],
                                "description": "Optional login credential type (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD')",
                            },
                            "retry_login": {
                                "type": ["boolean", "null"],
                                "description": "Set to true if the web page shows an error message about incorrect credentials.",
                            },
                        },
                        "required": ["target", "input_text", "login", "retry_login"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll",
                    "description": "Scroll the page up or down based on current viewport position",
                    "strict": True,
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
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": """Search Google for a query and navigate to results, switch to an existing open tab by index, or open search in a new tab. 
                Use this to navigate to any website, return to a previously opened page, or open searches in new tabs.""",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": ["string", "null"],
                                "description": "The search query to perform on Google (e.g., 'google accounts login', 'facebook login', 'amazon.com', etc.). Required if tab_index is not provided.",
                            },
                            "tab_index": {
                                "type": ["integer", "null"],
                                "description": """The zero-based index of an existing open tab to switch to (e.g., 0 for first tab, 1 for second tab). 
                            If provided, the agent will switch to this tab instead of performing a search. 
                            Use this when you want to return to a previously opened page. 
                            Check the OPEN BROWSER TABS section in your context to see available tab indices.""",
                            },
                            "new_tab": {
                                "type": "boolean",
                                "description": "If true, open the search in a new browser tab instead of navigating the current tab. Ignored if tab_index is provided.",
                            },
                        },
                        "required": ["query", "tab_index", "new_tab"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "extract",
                    "description": """Extract content from the current page. Two scenarios: 
                1) Basic extraction (use_rag=false) automatically saves content to task files for later reading, 
                2) RAG extraction (use_rag=true) stores chunks in vector database for semantic search via search_rag
                Only use this tool when the full contents, not just the title, are visible on the current page.""",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "use_rag": {
                                "type": "boolean",
                                "description": """If true, process content through RAG pipeline and store in vector database (use search_rag to query). 
                            If false, extract content and auto-save to task file (use file_system to read).""",
                            },
                            "file_name": {
                                "type": "string",
                                "description": "File name to save the extracted content to.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Description of what is being extracted (e.g., 'ML research paper', 'product specifications'). Used for tracking in agent state.",
                            },
                        },
                        "required": ["file_name", "description", "use_rag"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_system",
                    "description": """Interact with the file system to store, retrieve, or list files. 
                For multi-document tasks, make multiple read calls in one response to gather all content into context.""",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["write", "read", "list_files"],
                                "description": """Action to perform: 'write' to save content to file, 
                            'read' to read file content (make multiple read calls for multiple files), 
                            'list_files' to list saved files""",
                            },
                            "filename": {
                                "type": ["string", "null"],
                                "description": "Name of the file to read/write (required for write/read actions)",
                            },
                            "content": {
                                "type": ["string", "null"],
                                "description": "Content to write to file (required for write action)",
                            },
                        },
                        "required": ["action", "filename", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_rag",
                    "description": """Search the RAG vector database for semantically relevant content. 
                Use this to find information from previously extracted and processed web content.""",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for semantic search in RAG database",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results to return (default: 5, max: 20)",
                            },
                        },
                        "required": ["query", "top_k"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "done",
                    "description": "Signal that the user's task is completed or that the agent is unable to proceed. This will stop the agent execution.",
                    "strict": True,
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
                },
            },
        ],
        # "tool_choice": "required",
    })
    
    return base_config
