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
                    "name": "worker",
                    "description": "Assigns a chain of atomic, high-level instructions to a Worker agent for sequential execution. The prompt_chain should be a list of atomic browser actions or instructions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt_chain": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "A list of atomic, high-level instructions for the Worker Layer to execute sequentially.",
                            }
                        },
                        "required": ["prompt_chain"],
                    },
                },
            },
        ],
    }
