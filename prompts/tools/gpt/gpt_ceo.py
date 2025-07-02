def gpt_ceo(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-4o",
):
    return {
        "model": model,
        "input": [
            {"role": "user", "content": user_prompt},
            {"role": "system", "content": system_prompt},
        ],
        "tools": [
            {
                "type": "function",
                "name": "manager",
                "description": "Assigns a chain of high level subgoals to a manager agent for sequential execution."
                "Each manager should fulfill one part of the user prompt",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subgoal_chain": {
                            "type": "array",
                            "description": "A list of high level subgoals to be executed sequentially by the Manager Layer."
                            "Order tasks in chronological order. ",
                            "items": {
                                "type": "string",
                                "description": "A single subgoal for the manager to execute.",
                            },
                        },
                    },
                    "required": ["subgoal_chain"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "need_more_info",
                "description": "Request more information in the case the user's prompt is too vague or not actionable",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "A concise reason for requesting more information from the user",
                        },
                    },
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            },
        ],
    }
