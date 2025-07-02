def ceo_claude(
    user_prompt: str,
    system_prompt: str,
    model: str = "claude-3-5-haiku-latest",
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
                "name": "manager",
                "description": "Assigns a chain of high-level subgoals to a Manager agent for sequential execution."
                + "The subgoal_chain should be a list of high-level subgoals or objectives.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subgoal_chain": {
                            "type": "array",
                            "description": "A list of high-level subgoals to be executed sequentially by the Manager Layer."
                            + "Order subgoals in chronological order. ",
                        },
                    },
                    "required": ["subgoal_chain"],
                },
                "cache_control": {"type": "ephemeral"},
            },
            {
                "name": "need_more_info",
                "description": "Request more information in the case the user's prompt is too vague or not actionable",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "A concise reason for requesting more information from the user",
                        },
                    },
                },
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "system": [
            {
                "text": system_prompt,
                "type": "text",
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def pretty_print_tool_calls(tool_calls):
    for i, call in enumerate(tool_calls, 1):
        print(f"Manager Tool Call {i}:")
        subgoals = call['input'].get('subgoal_chain', [])
        for idx, subgoal in enumerate(subgoals, 1):
            print(f"  {idx}. {subgoal}")
        print()