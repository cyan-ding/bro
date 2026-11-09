"""System 1: a small local model picks one option from a fixed menu in a single token.

The decision is a probability distribution over typed choices (click element N, scroll, back,
or "hand over to the planner"), read from first-token logprobs. No text is generated, so a
wrong pick is a wrong click, never a hallucinated fact. Low confidence escalates to System 2.
"""

import math
import re
import string
import time
from typing import Dict, List, Optional

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .dsl import Action
from .llm import LOCAL_PREFIX
from .local_server import server_for
from .observe import Element, Observation, _format_element

LETTERS = string.ascii_uppercase
MAX_ELEMENT_OPTIONS = 20
ESCALATE_OPTIONS = {
    "type": "type text into a field (hand over to the planner)",
    "done": "the task is complete, give the answer (hand over to the planner)",
    "none": "none of these fit, think harder (hand over to the planner)",
}
STOPWORDS = {"the", "a", "an", "of", "on", "in", "to", "for", "and", "is", "what", "find", "report", "its", "with", "at", "use", "using"}

SYSTEM_PROMPT = """You are the reflex layer of a web browsing agent. Given the task, the most recent actions, and the current page, pick the single best next action from the lettered options. Prefer direct progress on the task. Pick a planner option when text must be typed, when the task is finished, or when no option clearly helps. Reply with one letter only."""

USER_TEMPLATE = """Task: {task}
Notes: {notes}
Recent actions:
{history}
Page: {title} | {url}
Visible text: {text}
Options:
{options}
Answer:"""


class Candidate(BaseModel):
    label: str
    action: Action
    line: str


class Decision(BaseModel):
    candidates: List[Candidate]
    choice: Optional[Candidate] = None
    confidence: float = 0.0
    distribution: Dict[str, float] = Field(default_factory=dict)
    latency_ms: int = 0
    prompt_tokens: int = 0
    escalate: bool = True
    reason: str = ""


def _task_terms(task: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", task.lower()) if len(w) > 2 and w not in STOPWORDS]


def _relevance(el: Element, terms: List[str]) -> float:
    haystack = (el.text + " " + " ".join(str(v) for v in el.attrs.values())).lower()
    score = sum(1.0 for t in terms if t in haystack)
    if el.tag in ("input", "textarea", "select") or el.attrs.get("role") in ("textbox", "searchbox", "combobox"):
        score += 1.5
    if el.tag == "button" or el.attrs.get("type") == "submit":
        score += 0.5
    return score


def _compact_line(line: str) -> str:
    """Shorter option text for a small reflex prompt: drop hrefs and long attribute values."""
    line = re.sub(r' href=\S+', "", line)
    line = re.sub(r'="([^"]{24})[^"]*"', r'="\1"', line)
    return line[:60]


def build_candidates(obs: Observation, task: str, max_elements: int = MAX_ELEMENT_OPTIONS, numeric: bool = False) -> List[Candidate]:
    """Element clicks in document order, then scroll/back, then planner hand-offs.

    Letter labels fit 20 relevance-filtered elements in one token; numeric labels cover every
    element (the model spells the number, confidence is the product of digit probabilities).
    """
    if numeric:
        chosen = list(obs.elements)
    else:
        terms = _task_terms(task)
        ranked = sorted(obs.elements, key=lambda e: _relevance(e, terms), reverse=True)[:max_elements]
        chosen = sorted(ranked, key=lambda e: e.index)
    candidates: List[Candidate] = []
    for el in chosen:
        candidates.append(Candidate(label="", action=Action(name="click", index=el.index), line=f"click {_format_element(el, obs.url)}"))
    candidates.append(Candidate(label="", action=Action(name="scroll", text="down"), line="scroll down"))
    if obs.scroll_y > 0:
        candidates.append(Candidate(label="", action=Action(name="scroll", text="up"), line="scroll up"))
    candidates.append(Candidate(label="", action=Action(name="back"), line="go back"))
    for key, desc in ESCALATE_OPTIONS.items():
        candidates.append(Candidate(label="", action=Action(name=key), line=desc))
    if numeric:
        for number, cand in enumerate(candidates):
            cand.label = str(number)
        return candidates
    for letter, cand in zip(LETTERS, candidates):
        cand.label = letter
    return candidates[: len(LETTERS)]


class LocalSystem1:
    """Scores the menu with a local model served by mlx_lm (OpenAI-compatible, logprobs enabled)."""

    def __init__(
        self,
        model: str,
        threshold: float = 0.6,
        max_text_chars: int = 500,
        base_url: Optional[str] = None,
        numeric: bool = False,
        openjev_style: bool = False,
        small: bool = False,
    ):
        self.model = model[len(LOCAL_PREFIX) :] if model.startswith(LOCAL_PREFIX) else model
        self.numeric = numeric
        self.openjev_style = openjev_style
        self.small = small
        if small:
            max_text_chars = 200
        self.threshold = threshold
        self.max_text_chars = max_text_chars
        self._client = AsyncOpenAI(base_url=base_url or server_for(self.model), api_key="local")

    def _prompt(self, task: str, notes: List[str], history: List[str], obs: Observation, candidates: List[Candidate]) -> str:
        return USER_TEMPLATE.format(
            task=task,
            notes="; ".join(notes) or "(none)",
            history="\n".join(history[-4:]) or "(none yet)",
            title=obs.title[:80],
            url=obs.url[:100],
            text=obs.text[: self.max_text_chars] or "(none)",
            options="\n".join(f"{c.label}. {c.line}" for c in candidates),
        )

    def _openjev_messages(self, task: str, notes: List[str], history: List[str], obs: Observation, candidates: List[Candidate]) -> List[Dict[str, str]]:
        """The layout OpenJev's reference shim uses: one user message, state then question then [A] options."""
        state = {
            "task": task,
            "notes": notes,
            "recent_actions": history[-4:],
            "page": {"title": obs.title[:80], "url": obs.url[:100], "visible_text": obs.text[: self.max_text_chars]},
        }
        import json

        lines = "\n".join(f"[{c.label}] {c.action.name}: {c.line}" for c in candidates)
        content = (
            f"State:\n{json.dumps(state, ensure_ascii=False)}\n\nQuestion: {SYSTEM_PROMPT.split('Reply with')[0].strip()} "
            f"Which option is the best next action?\nOptions:\n{lines}\n\nAnswer with the letter of the best option only."
        )
        return [{"role": "user", "content": content}]

    async def decide(self, task: str, notes: List[str], history: List[str], obs: Observation) -> Decision:
        candidates = build_candidates(obs, task, max_elements=10 if self.small else MAX_ELEMENT_OPTIONS, numeric=self.numeric)
        if self.small:
            for cand in candidates:
                cand.line = _compact_line(cand.line)
            history = history[-2:]
        decision = Decision(candidates=candidates)
        started = time.perf_counter()
        system = SYSTEM_PROMPT.replace("one letter only", "the option number only") if self.numeric else SYSTEM_PROMPT
        if self.openjev_style:
            messages = self._openjev_messages(task, notes, history, obs, candidates)
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": self._prompt(task, notes, history, obs, candidates)},
            ]
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=3 if self.numeric else 1,
                temperature=0,
                logprobs=True,
                top_logprobs=11,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception as exc:
            decision.reason = f"system1 error: {exc}"
            return decision
        decision.latency_ms = int((time.perf_counter() - started) * 1000)
        decision.prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
        content = response.choices[0].logprobs.content if response.choices[0].logprobs else None
        if not content:
            decision.reason = "no logprobs"
            return decision
        by_label = {c.label: c for c in candidates}
        probs: Dict[str, float] = {}
        if self.numeric:
            digits, logprob = "", 0.0
            for position in content:
                token = position.token.strip()
                if not token.isdigit():
                    break
                digits += token
                logprob += position.logprob
            if digits in by_label:
                probs[digits] = math.exp(logprob)
            for entry in content[0].top_logprobs:
                token = entry.token.strip()
                if token.isdigit() and token in by_label and token != digits and len(digits) == 1:
                    probs[token] = math.exp(entry.logprob)
        elif self.openjev_style:
            # OpenJev readout: softmax over every option letter's logprob (floor -30) at T=1.1.
            logprobs = {c.label: -30.0 for c in candidates}
            for entry in content[0].top_logprobs:
                token = entry.token.strip()
                if token in logprobs:
                    logprobs[token] = max(logprobs[token], entry.logprob)
            peak = max(logprobs.values())
            weights = {k: math.exp((v - peak) / 1.1) for k, v in logprobs.items()}
            total = sum(weights.values())
            probs = {k: w / total for k, w in weights.items()}
        else:
            for entry in content[0].top_logprobs:
                token = entry.token.strip().upper()
                if token in by_label:
                    probs[token] = probs.get(token, 0.0) + math.exp(entry.logprob)
        if not probs:
            decision.reason = "no option token in top logprobs"
            return decision
        label, confidence = max(probs.items(), key=lambda kv: kv[1])
        decision.distribution = dict(sorted(probs.items(), key=lambda kv: -kv[1]))
        decision.choice = by_label[label]
        decision.confidence = confidence
        if decision.choice.action.name in ESCALATE_OPTIONS:
            decision.reason = f"chose planner option '{decision.choice.action.name}'"
        elif confidence < self.threshold:
            decision.reason = f"confidence {confidence:.2f} below {self.threshold}"
        else:
            decision.escalate = False
            decision.reason = "confident"
        return decision


class JevSystem1:
    """Same menu, decided through a System One HTTP endpoint (state + typed questions in, probabilities out).

    Defaults to TypeSafe's Jev on OpenRouter; `endpoint` points it at any compatible local
    server instead, such as laya-serve or llama.cpp's /v1/systemone.
    """

    def __init__(
        self,
        threshold: float = 0.6,
        max_text_chars: int = 500,
        model: str = "typesafe/jev-1.14",
        numeric: bool = False,
        endpoint: Optional[str] = None,
    ):
        import os

        from bro.utils.env_loader import load_env_files

        load_env_files()
        self.numeric = numeric
        self.model = model
        self.threshold = threshold
        self.max_text_chars = max_text_chars
        self._path = "/v1/systemone" if endpoint else "/alpha/decisions"
        self._client = httpx.AsyncClient(
            base_url=endpoint or "https://openrouter.ai/api",
            headers={} if endpoint else {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"},
            timeout=30,
        )

    async def decide(self, task: str, notes: List[str], history: List[str], obs: Observation) -> Decision:
        candidates = build_candidates(obs, task, numeric=self.numeric)
        decision = Decision(candidates=candidates)
        state = USER_TEMPLATE.format(
            task=task,
            notes="; ".join(notes) or "(none)",
            history="\n".join(history[-4:]) or "(none yet)",
            title=obs.title[:80],
            url=obs.url[:100],
            text=obs.text[: self.max_text_chars] or "(none)",
            options="\n".join(f"{c.label}. {c.line}" for c in candidates),
        ).split("\nOptions:")[0]
        body = {
            "model": self.model,
            "state": state,
            "questions": {
                "next": {
                    "type": "choice",
                    "instructions": SYSTEM_PROMPT.replace("Reply with one letter only.", "Which option is the best next action?"),
                    "criteria": {c.label: c.line[:160] for c in candidates},
                }
            },
        }
        started = time.perf_counter()
        try:
            http = await self._client.post(self._path, json=body)
            http.raise_for_status()
            response = http.json()
        except Exception as exc:
            decision.reason = f"jev error: {exc}"
            return decision
        decision.latency_ms = int((time.perf_counter() - started) * 1000)
        answer = response.get("answers", {}).get("next", {})
        probs = {k: float(v) for k, v in (answer.get("probabilities") or {}).items()}
        decision.prompt_tokens = int(response.get("usage", {}).get("input_tokens", 0) or 0)
        if not probs:
            decision.reason = f"jev returned no probabilities: {str(response)[:120]}"
            return decision
        by_label = {c.label: c for c in candidates}
        label, confidence = max(probs.items(), key=lambda kv: kv[1])
        decision.distribution = dict(sorted(probs.items(), key=lambda kv: -kv[1]))
        decision.choice = by_label.get(label)
        decision.confidence = confidence
        if decision.choice is None:
            decision.reason = f"unknown label {label}"
        elif decision.choice.action.name in ESCALATE_OPTIONS:
            decision.reason = f"chose planner option '{decision.choice.action.name}'"
        elif confidence < self.threshold:
            decision.reason = f"confidence {confidence:.2f} below {self.threshold}"
        else:
            decision.escalate = False
            decision.reason = "confident"
        return decision


def ideal_label(action: Action, candidates: List[Candidate]) -> str:
    """The menu label a perfect System 1 would have picked given the planner's action."""
    for cand in candidates:
        if cand.action.name == action.name and cand.action.index == action.index and cand.action.text == action.text:
            return cand.label
    name = "type" if action.name == "type" else "done" if action.name == "done" else "none"
    return next(c.label for c in candidates if c.action.name == name)


def make_system1(spec: str, threshold: float = 0.6):
    """`jev`, `systemone@http://host:port[|model]`, `local/<model>`; flags `#num`, `#oj`, `#small`."""
    base, _, flags = spec.partition("#")
    numeric = "num" in flags
    if base == "jev":
        return JevSystem1(threshold, numeric=numeric)
    if base.startswith("systemone@"):
        endpoint, _, model = base[len("systemone@") :].partition("|")
        return JevSystem1(threshold, numeric=numeric, endpoint=endpoint, model=model or "laya")
    return LocalSystem1(base, threshold, numeric=numeric, openjev_style="oj" in flags, small="small" in flags)
