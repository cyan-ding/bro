def gpt_summarizer(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-4o",
):
    return {
        "model": model,
        "input": [
            {"role": "user", "content": user_prompt},
            {"role": "system", "content": system_prompt},
        ]
    }
