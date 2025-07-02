def ceo_tool(user_prompt: str, system_prompt: str, model):
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
                    "name": "manager",
                    "description": "Assigns a chain of high-level subgoals to a Manager agent for sequential execution. The subgoal_chain should be a list of high-level subgoals or objectives.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subgoal_chain": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "A list of high-level subgoals to be executed sequentially by the Manager Layer.",
                            }
                        },
                        "required": ["subgoal_chain"],
                    },
                },
            },
        ],
    }
