def manager_tool(user_prompt: str, system_prompt: str, model):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "stream": False,
        "tool_choice": "required",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click on a button or button-like object displayed in the browser. "
                    "The 'target' argument must be a literal, observable description of the UI element, "
                    "such as the exact text, label, or aria-label as it appears in the DOM. "
                    "Example: 'button with text \"Sign in\"'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "Given the provided task, provide the name of the object on the screen the user would interact with and enter text into",
                            }
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "input_text",
                    "description": "Enter text into a text area, text box, or text field in the browser. "
                    "The 'target' argument must be a literal, observable description of the UI element, "
                    "such as the exact placeholder, label, or aria-label as it appears in the DOM. "
                    "Example: 'input field with placeholder \"Email\"'."
                    "The 'input' argument must be a precise match to what the user wants inputed into the text field.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "A concise description of the kind of text input to fulfill the provided task",
                            },
                            "input": {
                                "type": "string",
                                "description": "Text to input to the text field that matches the user's prompt",
                            },
                        },
                        "required": ["target", "input"],
                    },
                },
            },
        ],
    }
