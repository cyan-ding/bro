def manager_claude(
    user_prompt: str,
    system_prompt: str,
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.1,
    stream: bool = False,
    max_tokens: int = 1024,
):
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
        "tools": [
            {
                "name": "worker",
                "description": "Assigns a chain of low-level atomic tasks to a worker agent for sequential execution."
                + "The subgoal_chain should be a list of high-level subgoals or objectives.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt_chain": {
                            "type": "array",
                            "description": "A list of low level atomic tasks to be executed sequentially by the Manager Layer."
                            + "Order tasks in chronological order. ",
                        },
                    },
                    "required": ["prompt_chain"],
                },
                "cache_control": {"type": "ephemeral"},
            },
            # {
            #     "name": "need_more_info",
            #     "description": "Request more information in the case the user's prompt is too vague or not actionable",
            #     "input_schema": {
            #         "type": "object",
            #         "properties": {
            #             "reason": {
            #                 "type": "string",
            #                 "description": "A concise reason for requesting more information from the user",
            #             },
            #         },
            #     },
            #     "cache_control": {"type": "ephemeral"},
            # },
        ],
        "system": [
            {
                "text": system_prompt,
                "type": "text",
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }
