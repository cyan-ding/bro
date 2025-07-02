def gpt_manager(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-4.1",
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
                "name": "worker",
                "description": "Assigns a chain of low-level atomic tasks to a worker agent for sequential execution."
                "Each atomic task MUST follow the user's specified website or tool exactly. Do NOT substitute or add alternatives."
                "Each atomic task MUST target only a single object or action (e.g., one website, one button, one field). "
                "Do NOT combine multiple targets or actions in a single task. ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt_chain": {
                            "type": "array",
                            "description": "A list of low level atomic tasks to be executed sequentially by the Manager Layer."
                            + "Order tasks in chronological order. ",
                            "items": {
                                "type": "string",
                                "description": "A single atomic task for the worker to execute.",
                            },
                        },
                    },
                    "required": ["prompt_chain"],
                    "additionalProperties": False,
                },
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
        "temperature": 0.5,
    }
