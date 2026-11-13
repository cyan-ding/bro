"""The fast agent loop: observe (text only) -> one short LLM call -> act -> settle."""

import asyncio
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from patchright.async_api import BrowserContext, Page
from pydantic import BaseModel, Field

from .dsl import Action, parse
from .llm import ChatModel, Completion
from .observe import Element, Observation, format_elements, observe, observe_lean, signature
from .prompts import FINAL_STEP_SUFFIX, REPLAN_SUFFIX, USER_TEMPLATE, VERIFY_SUFFIX, system_prompt
from .settle import settle
from .system1 import Decision, ideal_label

PAGE_CHANGING = {"click", "goto", "search", "back", "press", "scroll", "select"}
ALWAYS_RUN = {"done"}
MAX_ACTIONS_PER_STEP = 3
NAV_TIMEOUT_MS = 45000
MAX_VETOES = 2
HEDGE = re.compile(r"\b(unable|cannot|could not|can't|not (?:be )?(?:found|visible|available|determined|completed)|may be needed|further (?:scrolling|search)|technical issues)\b", re.IGNORECASE)


class StepRecord(BaseModel):
    step: int
    url: str
    output: str
    actions: List[str] = Field(default_factory=list)
    results: List[str] = Field(default_factory=list)
    observe_ms: int = 0
    llm_ms: int = 0
    act_ms: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    prompt_chars: int = 0
    system: str = "s2"
    s1: Dict[str, Any] = Field(default_factory=dict)
    shadow: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    state: Optional[Dict[str, Any]] = None


class RunResult(BaseModel):
    task: str
    model: str
    answer: Optional[str] = None
    finished: bool = False
    error: Optional[str] = None
    steps: List[StepRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    total_ms: int = 0


def _decision_summary(decision: Decision) -> Dict[str, Any]:
    return {
        "label": decision.choice.label if decision.choice else None,
        "action": str(decision.choice.action) if decision.choice else None,
        "confidence": round(decision.confidence, 4),
        "latency_ms": decision.latency_ms,
        "prompt_tokens": decision.prompt_tokens,
        "escalate": decision.escalate,
        "reason": decision.reason,
        "top": {k: round(v, 4) for k, v in list(decision.distribution.items())[:5]},
        "menu_size": len(decision.candidates),
    }


OnStep = Callable[[StepRecord, Observation], Awaitable[None]]
OnDone = Callable[[str], Awaitable[Tuple[str, str]]]
GetMessages = Callable[[], List[str]]


class FastAgent:
    def __init__(
        self,
        model: str,
        reason: bool = False,
        max_elements: int = 80,
        max_text_chars: int = 800,
        history_len: int = 8,
        max_tokens: int = 400,
        on_step: Optional[OnStep] = None,
        on_done: Optional[OnDone] = None,
        get_messages: Optional[GetMessages] = None,
        verify: bool = False,
        reject_hedged_done: bool = False,
        observer: str = "lean",
        system1: Optional[Any] = None,
        shadow: Optional[Dict[str, Any]] = None,
        log_states: bool = False,
    ):
        self.log_states = log_states
        self.system1 = system1
        self.shadow = shadow or {}
        self.observer = observer
        self.verify = verify
        self.reject_hedged_done = reject_hedged_done
        self.vetoes = 0
        self.on_step = on_step
        self.on_done = on_done
        self.get_messages = get_messages
        self.llm = ChatModel(model, max_tokens=max_tokens)
        self.model = model
        self.system = system_prompt(reason)
        self.max_elements = max_elements
        self.max_text_chars = max_text_chars
        self.history_len = history_len
        self.history: List[str] = []
        self.notes: List[str] = []
        self._new_pages: List[Page] = []
        self._pending_obs: Optional[Observation] = None
        self._noop: Dict[str, int] = {}
        self._stalled_steps = 0
        self._step_effect = False
        self._seen: List[str] = []

    def _on_new_page(self, page: Page) -> None:
        self._new_pages.append(page)

    @staticmethod
    def _dismiss_dialogs(page: Page) -> None:
        page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))

    def _build_user_prompt(self, task: str, obs: Observation) -> str:
        history = "\n".join(self.history[-self.history_len :]) or "(none yet)"
        return USER_TEMPLATE.format(
            task=task,
            notes="; ".join(self.notes) or "(none)",
            history=history,
            title=obs.title[:80],
            url=obs.url[:120],
            scroll=obs.scroll_summary(),
            text=obs.text[: self.max_text_chars] or "(none)",
            elements=format_elements(obs, self.max_elements),
        )

    async def run(
        self,
        context: BrowserContext,
        page: Page,
        task: str,
        start_url: Optional[str] = None,
        max_steps: int = 25,
    ) -> RunResult:
        result = RunResult(task=task, model=self.model)
        started = time.perf_counter()
        context.on("page", self._on_new_page)
        self._dismiss_dialogs(page)
        try:
            if start_url:
                await self._goto(page, start_url)
            parse_failures = 0
            for step in range(1, max_steps + 1):
                if self._new_pages:
                    page = self._new_pages[-1]
                    self._new_pages.clear()
                    self._dismiss_dialogs(page)
                    await page.bring_to_front()
                    await settle(page)
                if self.get_messages:
                    for message in self.get_messages():
                        task += f"\nUser says: {message}"
                record = StepRecord(step=step, url=page.url, output="")
                observe_started = time.perf_counter()
                obs = self._pending_obs if self._pending_obs is not None and self._pending_obs.url == page.url else await self._observe(page)
                self._pending_obs = None
                for element in obs.elements:
                    if self._noop.get(element.fingerprint(), 0) >= 1:
                        element.note = "(clicking this did nothing)"
                obs.elements = [e for e in obs.elements if self._noop.get(e.fingerprint(), 0) < 2]
                if self._stalled_steps >= 4 and start_url and page.url != start_url:
                    await self._goto(page, start_url)
                    obs = await self._observe(page)
                    self.history.append(f"{step}. (stuck for {self._stalled_steps} steps; returned to the start page, try a different route)")
                    self._stalled_steps = 2
                sig_now = signature(obs)
                if sig_now not in self._seen:
                    self._seen = (self._seen + [sig_now])[-40:]
                record.observe_ms = int((time.perf_counter() - observe_started) * 1000)

                if self.log_states:
                    record.state = {"obs": obs.model_dump(), "history": list(self.history), "notes": list(self.notes), "task": task}
                user_prompt = self._build_user_prompt(task, obs)
                if self._stalled_steps >= 2:
                    tried = sorted({h.split(" -> ")[0].split(". ", 1)[-1] for h in self.history[-6:] if " -> " in h})
                    user_prompt += REPLAN_SUFFIX.format(tried="; ".join(tried)[:400])
                if step == max_steps:
                    user_prompt += FINAL_STEP_SUFFIX
                record.prompt_chars = len(self.system) + len(user_prompt)

                shadow_decisions: Dict[str, Decision] = {}
                if step > 1:
                    for name, scorer in self.shadow.items():
                        shadow_decisions[name] = await scorer.decide(task, self.notes, self.history, obs)
                reflex: Optional[Decision] = None
                if self.system1 is not None and 1 < step < max_steps:
                    reflex = await self.system1.decide(task, self.notes, self.history, obs)
                    record.s1 = _decision_summary(reflex)
                if reflex is not None and not reflex.escalate and reflex.choice is not None:
                    record.system = "s1"
                    record.llm_ms = reflex.latency_ms
                    record.prompt_tokens = reflex.prompt_tokens
                    record.output = f"{reflex.choice.label} ({reflex.confidence:.2f})"
                    actions = [reflex.choice.action]
                else:
                    completion = await self._complete(user_prompt)
                    record.output = completion.text
                    record.llm_ms = completion.latency_ms + (reflex.latency_ms if reflex else 0)
                    record.prompt_tokens = completion.prompt_tokens
                    record.cached_tokens = completion.cached_tokens
                    record.completion_tokens = completion.completion_tokens
                    actions = parse(completion.text)
                if shadow_decisions:
                    first = actions[0] if actions else Action(name="none")
                    for name, decision in shadow_decisions.items():
                        summary = _decision_summary(decision)
                        ideal = ideal_label(first, decision.candidates) if decision.candidates else ""
                        summary["ideal"] = ideal
                        summary["agrees"] = bool(decision.choice and decision.choice.label == ideal)
                        summary["menu_covers"] = ideal not in {c.label for c in decision.candidates if c.action.name == "none"}
                        record.shadow[name] = summary
                if not actions:
                    parse_failures += 1
                    draft = " ".join(completion.text.split())[:300]
                    self.history.append(
                        f'{step}. (invalid reply, no action line; your draft was: "{draft}") -> reply with action lines only; if the draft contains the answer, reply done "answer"'
                    )
                    result.steps.append(record)
                    if parse_failures >= 3:
                        result.error = "model produced no valid actions three times"
                        break
                    continue
                parse_failures = 0

                act_started = time.perf_counter()
                page_changed = False
                self._step_effect = False
                for action in actions[:MAX_ACTIONS_PER_STEP]:
                    if page_changed and action.name not in ALWAYS_RUN:
                        self.history.append(f"{step}. {action} -> skipped (page changed)")
                        continue
                    outcome = await self._execute(page, action, obs)
                    record.actions.append(str(action))
                    record.results.append(outcome)
                    self.history.append(f"{step}. {action} -> {outcome}")
                    if action.name == "done":
                        veto = await self._veto(user_prompt, action.text) if self.verify else None
                        if veto is None and self.reject_hedged_done and step < max_steps and HEDGE.search(action.text) and self.vetoes < MAX_VETOES:
                            self.vetoes += 1
                            veto = "that is not an answer; keep working (search differently, open the item, scroll) until you have the facts"
                        if veto:
                            self.history.append(f"{step}. (self-check rejected the answer: {veto}; keep working)")
                            break
                        result.answer = action.text
                        result.finished = True
                        break
                    if outcome.startswith("error") or action.name in PAGE_CHANGING:
                        page_changed = True
                record.act_ms = int((time.perf_counter() - act_started) * 1000)
                acted = any(a.name not in ("note", "done") for a in actions[:MAX_ACTIONS_PER_STEP])
                self._stalled_steps = 0 if (self._step_effect or not acted) else self._stalled_steps + 1
                result.steps.append(record)
                if self.on_step:
                    await self.on_step(record, obs)
                if result.finished:
                    if not self.on_done:
                        break
                    decision, extra = await self.on_done(result.answer or "")
                    if decision == "done":
                        break
                    result.finished = False
                    if decision == "modify":
                        task += f"\nAdditional instructions: {extra}"
                    self.history.append(f"{step}. (user asked to continue: {extra or 'they intervened manually'})")
                    continue
                self._detect_loop()
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            context.remove_listener("page", self._on_new_page)
        result.notes = list(self.notes)
        result.total_ms = int((time.perf_counter() - started) * 1000)
        return result

    async def _observe(self, page: Page) -> Observation:
        observer = observe_lean if self.observer == "lean" else observe
        try:
            return await observer(page, self.max_text_chars)
        except Exception:
            await settle(page, max_ms=3000)
            return await observer(page, self.max_text_chars)

    async def _target(self, page: Page, element: Element):
        """Locator (XPath observer) or ElementHandle (lean observer) for an element, None if gone."""
        if element.ref is not None:
            handle = (await page.evaluate_handle(f"() => window.__broEls && window.__broEls[{element.ref}]")).as_element()
            if handle is None or not await handle.evaluate("el => el.isConnected"):
                return None
            return handle
        locator = self._locator(page, element).first
        return locator if await locator.count() else None

    async def _complete(self, user_prompt: str) -> Completion:
        try:
            return await self.llm.complete(self.system, user_prompt)
        except Exception as exc:
            return Completion(text=f"# llm error: {exc}")

    async def _veto(self, user_prompt: str, answer: str) -> Optional[str]:
        """Cheap self-check that reuses the cached prompt prefix; returns a reason to reject, else None."""
        if self.vetoes >= MAX_VETOES:
            return None
        check = user_prompt + VERIFY_SUFFIX.format(answer=answer)
        try:
            reply = (await self.llm.complete(self.system, check)).text.strip()
        except Exception:
            return None
        if reply.lower().startswith("yes"):
            return None
        self.vetoes += 1
        return reply[:160]

    def _detect_loop(self) -> None:
        recent = [h.split(" -> ")[0].split(". ", 1)[-1] for h in self.history[-3:]]
        if len(recent) == 3 and len(set(recent)) == 1:
            self.history.append("(you repeated the same action 3 times; it is not working, change approach)")

    async def _goto(self, page: Page, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception:
            # Slow page: settle for the first response instead of failing the whole step.
            await page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
        await settle(page)

    def _locator(self, page: Page, element: Element):
        if element.iframe_xpath:
            return page.frame_locator(f"xpath={element.iframe_xpath}").locator(f"xpath={element.xpath}")
        return page.locator(f"xpath={element.xpath}")

    async def _after(self, page: Page, before: Observation, element: Optional[Element] = None) -> str:
        """Observe after an action; say whether anything visible changed and remember no-op clicks."""
        try:
            after = await self._observe(page)
        except Exception:
            return "ok"
        self._pending_obs = after
        sig = signature(after)
        novel = sig not in self._seen
        self._seen = (self._seen + [sig])[-40:]
        if after.url != before.url or after.title != before.title:
            if novel:
                self._step_effect = True
                return f"ok, now at {after.title}"
        elif sig != signature(before):
            if novel:
                self._step_effect = True
                return "ok"
        else:
            if element is not None:
                self._noop[element.fingerprint()] = self._noop.get(element.fingerprint(), 0) + 1
            return "ok, but nothing on the page changed"
        # The page changed, but only back to a state already seen: toggling, not progress.
        if element is not None:
            self._noop[element.fingerprint()] = self._noop.get(element.fingerprint(), 0) + 1
        return "ok, but this only returned to a page state you had already seen (no progress)"

    async def _execute(self, page: Page, action: Action, obs: Observation) -> str:
        try:
            if action.name == "note":
                self.notes.append(action.text)
                return "saved"
            if action.name == "done":
                return "finished"
            if action.name == "wait":
                await settle(page, quiet_ms=400, max_ms=3000)
                return "ok"
            if action.name == "goto":
                await self._goto(page, action.text)
                self._step_effect = True
                return f"ok, now at {await page.title()}"
            if action.name == "search":
                await self._goto(page, f"https://www.google.com/search?q={quote_plus(action.text)}")
                self._step_effect = True
                return f"ok, now at {await page.title()}"
            if action.name == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
                await settle(page)
                return await self._after(page, obs)
            if action.name == "press":
                await page.keyboard.press(action.text or "Enter")
                await settle(page)
                return await self._after(page, obs)
            if action.name == "scroll":
                sign = -1 if action.text == "up" else 1
                await page.evaluate(f"window.scrollBy(0, {sign} * window.innerHeight * 0.8)")
                await settle(page, quiet_ms=100, max_ms=600)
                outcome = await self._after(page, obs)
                return outcome if "nothing" not in outcome else "ok, but the page did not scroll (already at the end)"
            element = obs.element(action.index or -1)
            if element is None:
                return f"error: no element with index {action.index}"
            locator = await self._target(page, element)
            if locator is None:
                return "error: element is no longer on the page"
            if action.name == "click":
                try:
                    await locator.click(timeout=3000)
                except Exception:
                    await locator.evaluate("el => el.click()")
                await settle(page)
                return await self._after(page, obs, element)
            if action.name == "type":
                try:
                    await locator.fill(action.text, timeout=3000)
                except Exception:
                    await locator.click(timeout=2000)
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.type(action.text)
                await settle(page, quiet_ms=100, max_ms=600)
                self._step_effect = True
                return "ok"
            if action.name == "select":
                try:
                    await locator.select_option(label=action.text, timeout=3000)
                except Exception:
                    await locator.select_option(value=action.text, timeout=3000)
                await settle(page)
                return await self._after(page, obs, element)
            return f"error: unknown action {action.name}"
        except Exception as exc:
            message = str(exc).splitlines()[0][:120]
            return f"error: {message}"
