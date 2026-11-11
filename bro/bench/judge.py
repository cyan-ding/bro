"""Score a run's answer against a task's check."""

import re
from typing import List

import litellm
from pydantic import BaseModel

JUDGE_MODEL = "openrouter/google/gemini-2.5-flash"


class Task(BaseModel):
    id: str
    task: str
    url: str
    check: str
    expected: List[str]


class Verdict(BaseModel):
    success: bool
    reason: str


async def judge(task: Task, answer: str) -> Verdict:
    text = (answer or "").lower()
    if not text.strip():
        return Verdict(success=False, reason="no answer")
    if task.check == "contains":
        hit = any(e.lower() in text for e in task.expected)
        return Verdict(success=hit, reason=f"contains {task.expected}")
    if task.check == "contains_all":
        hit = all(e.lower() in text for e in task.expected)
        return Verdict(success=hit, reason=f"contains all {task.expected}")
    if task.check == "regex":
        hit = any(re.search(e, text, re.IGNORECASE) for e in task.expected)
        return Verdict(success=hit, reason=f"regex {task.expected}")
    prompt = (
        f"Task given to a web agent: {task.task}\n"
        f"Agent's final answer: {answer}\n"
        f"Success criterion: the answer provides {task.expected[0]}.\n"
        "Judge only whether the answer is a concrete, plausible, complete response to the task: PASS if it gives the "
        "requested information for every part of the task (formatting does not matter); FAIL if it refuses, reports "
        "an error, is cut off mid-sentence, or omits a requested part.\n"
        "Reply with exactly one word: PASS or FAIL."
    )
    response = await litellm.acompletion(
        model=JUDGE_MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=5, temperature=0, timeout=60
    )
    verdict = (response.choices[0].message.content or "").strip().upper()
    return Verdict(success=verdict.startswith("PASS"), reason=f"llm judge: {verdict}")
