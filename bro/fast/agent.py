"""The fast agent loop: observe (text only) -> one short LLM call -> act -> settle."""

import asyncio
import base64
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from patchright.async_api import BrowserContext, Page
from pydantic import BaseModel, Field

from .dsl import Action, parse
from .llm import ChatModel, Completion
from .observe import Element, Observation, StableIds, format_elements, observe, observe_lean, signature
from .prompts import DELIVER_SUFFIX, FINAL_STEP_SUFFIX, REPLAN_SUFFIX, USER_TEMPLATE, VERIFY_SUFFIX, VISION_CHECK_SUFFIX, VISION_STALL_SUFFIX, system_prompt
from .browser import FocusWatch, prepare_page
from .settle import settle, track_network
from .system1 import Decision, ideal_label

PAGE_CHANGING = {"click", "goto", "search", "back", "press", "scroll", "select", "find"}
ALWAYS_RUN = {"done"}
MAX_ACTIONS_PER_STEP = 3
NAV_TIMEOUT_MS = 45000
MAX_VETOES = 2
CONTROL_ROLES = {"checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio", "option", "tab"}
CONTROL_STATE_JS = """el => {
  const pick = 'input[type=checkbox], input[type=radio]';
  let box = (el.tagName === 'INPUT' && /checkbox|radio/.test(el.type)) ? el : null;
  if (!box && el.tagName === 'LABEL' && el.control) box = el.control;
  if (!box) { const inner = el.querySelectorAll(pick); if (inner.length === 1) box = inner[0]; }
  if (box) return box.checked ? 'checked' : 'unchecked';
  for (const attr of ['aria-checked', 'aria-pressed', 'aria-selected']) {
    const val = el.getAttribute(attr);
    const word = attr === 'aria-checked' ? 'checked' : attr.slice(5);
    if (val === 'true') return word;
    if (val === 'false') return 'not ' + word;
    if (val === 'mixed') return 'partly ' + word;
  }
  const state = el.getAttribute('data-state');
  return state ? 'state=' + state : null;
}"""
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
    vision: bool = False
    focus: List[str] = Field(default_factory=list)


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
        vision: bool = False,
        time_budget_s: float = 0,
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
        self.vision = vision
        self.time_budget_s = time_budget_s
        self.ids = StableIds()
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
        self._focus_notes: List[str] = []
        self._step, self._max_steps = 0, 0
        self._stalled_steps = 0
        self._step_effect = False
        self._seen: List[str] = []
        self._last_action: Optional[str] = None
        self._current_action: Optional[str] = None

    def _on_new_page(self, page: Page) -> None:
        self._new_pages.append(page)

    @staticmethod
    def _dismiss_dialogs(page: Page) -> None:
        page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))

    def _build_user_prompt(self, task: str, obs: Observation) -> str:
        history = "\n".join(self.history[-self.history_len :]) or "(none yet)"
        return USER_TEMPLATE.format(
            task=task,
            progress=f"Step: {self._step} of {self._max_steps}; give the answer before the steps run out\n" if self._max_steps else "",
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
        track_network(page)
        try:
            if start_url:
                await self._goto(page, start_url)
            parse_failures = 0
            for step in range(1, max_steps + 1):
                self._step, self._max_steps = step, max_steps
                if self._new_pages:
                    page = self._new_pages[-1]
                    self._new_pages.clear()
                    self._dismiss_dialogs(page)
                    track_network(page)
                    await prepare_page(page)  # background tab: focus emulation instead of raising the window
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
                        element.note = "(clicking this does not work)"
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
                image: Optional[str] = None
                if self._stalled_steps >= 2:
                    tried = sorted({h.split(" -> ")[0].split(". ", 1)[-1] for h in self.history[-6:] if " -> " in h})
                    user_prompt += REPLAN_SUFFIX.format(tried="; ".join(tried)[:400])
                    if self.vision:
                        image = await self._screenshot(page)
                        if image:
                            user_prompt += VISION_STALL_SUFFIX
                            record.vision = True
                out_of_time = self.time_budget_s and (time.perf_counter() - started) > self.time_budget_s
                if step == max_steps or out_of_time:
                    user_prompt += FINAL_STEP_SUFFIX if step == max_steps else DELIVER_SUFFIX
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
                    completion = await self._complete(user_prompt, image)
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
                    record.focus, self._focus_notes = self._focus_notes, []
                    result.steps.append(record)
                    if parse_failures >= 3:
                        result.error = "model produced no valid actions three times"
                        break
                    continue
                parse_failures = 0
                if self.vision and any(a.name == "done" for a in actions) and step < max_steps and not out_of_time:
                    proposed = next(a for a in actions if a.name == "done")
                    actions = await self._vision_check(page, user_prompt, proposed, actions)
                    record.vision = True
                if any(a.name == "done" and len(a.text.strip()) < 8 for a in actions) and step < max_steps and self.vetoes < MAX_VETOES:
                    self.vetoes += 1
                    self.history.append(f"{step}. done -> rejected: empty answer; give the actual facts")
                    actions = [a for a in actions if a.name != "done"] or [Action(name="read")]

                act_started = time.perf_counter()
                page_changed = False
                self._step_effect = False
                for action in actions[:MAX_ACTIONS_PER_STEP]:
                    if page_changed and action.name not in ALWAYS_RUN:
                        self.history.append(f"{step}. {action} -> skipped (page changed)")
                        continue
                    self._current_action = str(action)
                    watch = FocusWatch()
                    await watch.start()
                    outcome = await self._execute(page, action, obs)
                    self._last_action = self._current_action
                    note = await watch.check(str(action))
                    if note:
                        self._focus_notes.append(note)
                    record.actions.append(str(action))
                    record.results.append(outcome)
                    self.history.append(f"{step}. {action} -> {outcome}")
                    if action.name == "done":
                        veto = await self._veto(user_prompt, action.text) if self.verify and step < max_steps and not out_of_time else None
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
                record.focus, self._focus_notes = self._focus_notes, []
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
            obs = await observer(page, self.max_text_chars)
        except Exception:
            await settle(page, max_ms=3000)
            obs = await observer(page, self.max_text_chars)
        if self.observer == "lean":
            self.ids.assign(obs)
        return obs

    async def _target(self, page: Page, element: Element):
        """Locator (XPath observer) or ElementHandle (lean observer) for an element, None if gone."""
        if element.ref is not None:
            scope = page
            if element.frame_url:
                scope = next((f for f in page.frames if f.url == element.frame_url), None)
                if scope is None:
                    return None
            handle = (await scope.evaluate_handle(f"() => window.__broEls && window.__broEls[{element.ref}]")).as_element()
            if handle is None or not await handle.evaluate("el => el.isConnected"):
                return None
            return handle
        locator = self._locator(page, element).first
        return locator if await locator.count() else None

    async def _complete(self, user_prompt: str, image: Optional[str] = None) -> Completion:
        try:
            return await self.llm.complete(self.system, user_prompt, image_b64=image)
        except Exception as exc:
            return Completion(text=f"# llm error: {exc}")

    async def _veto(self, user_prompt: str, answer: str) -> Optional[str]:
        """Requirement-by-requirement check of a proposed answer (reuses the cached prefix); returns what is missing, else None."""
        if self.vetoes >= MAX_VETOES:
            return None
        check = user_prompt + VERIFY_SUFFIX.format(answer=answer)
        try:
            reply = (await self.llm.complete(self.system, check)).text.strip()
        except Exception:
            return None
        rejected = re.search(r"REJECTED:?\s*(.*)", reply)
        if rejected is None:
            return None
        self.vetoes += 1
        return (rejected.group(1).strip() or "a part of the task is missing")[:200]

    async def _screenshot(self, page: Page) -> Optional[str]:
        watch = FocusWatch()
        await watch.start()
        try:
            data = await page.screenshot(type="jpeg", quality=70)
        except Exception:
            return None
        note = await watch.check("screenshot")
        if note:
            self._focus_notes.append(note)
        return base64.b64encode(data).decode()

    async def _vision_check(self, page: Page, user_prompt: str, proposed: Action, actions: List[Action]) -> List[Action]:
        """Ask the planner to confirm a proposed answer against a screenshot; it may correct it or keep working."""
        image = await self._screenshot(page)
        if not image:
            return actions
        reply = await self._complete(user_prompt + VISION_CHECK_SUFFIX.format(answer=proposed.text[:300]), image)
        verdict = reply.text.strip()
        if verdict.upper().startswith("CONFIRMED"):
            return actions
        if not verdict.upper().startswith("REJECTED"):
            return actions
        reason = verdict.splitlines()[0][len("REJECTED") :].strip(" :-")[:160]
        self.history.append(f"(screenshot check rejected the answer: {reason or 'not supported by the page'}; keep working)")
        checked = [a for a in parse(reply.text) if a.name != "done"]
        return checked or [Action(name="read")]

    @staticmethod
    def _is_control(element: Element) -> bool:
        """Checkbox, radio, switch, option, tab or a filter wrapper that reports one of those states."""
        role = element.attrs.get("role", "")
        return (
            element.attrs.get("type") in ("checkbox", "radio")
            or role in CONTROL_ROLES
            or any(key in element.attrs for key in ("checked", "selected", "pressed", "state"))
        )

    @staticmethod
    async def _control_state(locator: Any) -> Optional[str]:
        """'checked', 'unchecked', 'not pressed', 'state=open', ... for a control (or the one input it wraps); None otherwise."""
        try:
            return await locator.evaluate(CONTROL_STATE_JS)
        except Exception:
            return None

    async def _with_state(self, locator: Any, before: Optional[str], outcome: str) -> str:
        """Say whether a clicked control actually changed, so the model does not assume a filter is on when it is not."""
        if before is None:
            return outcome
        after = await self._control_state(locator)
        if after is None or outcome.startswith("ok, now at"):
            return outcome
        if after == before:
            return f"{outcome}; the control did not change (still {after}), try another element or approach"
        return f"{outcome}; the control is now {after}"

    def _refuse(self, element: Element, message: str) -> str:
        """A click that cannot land counts as a no-op, so the element is flagged and then dropped like any inert one."""
        self._noop[element.fingerprint()] = self._noop.get(element.fingerprint(), 0) + 1
        return message

    async def _covered_by(self, page: Page, element: Element):
        """Find a point of `element` that a click actually reaches.

        Returns None (center is fine), a dict {x, y} offset of a clear point inside the element,
        or a string: "disabled", "hidden", "gone", "ref:N" (covered by listed element N), "other:tag".
        """
        scope = page
        if element.frame_url:
            scope = next((f for f in page.frames if f.url == element.frame_url), None)
            if scope is None:
                return "gone"
        try:
            hit = await scope.evaluate(
                """(ref) => {
                    const el = window.__broEls && window.__broEls[ref]; if (!el) return "gone";
                    if (el.disabled || el.getAttribute("aria-disabled") === "true") return "disabled";
                    el.scrollIntoView({block: "center", inline: "center"});
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return "hidden";
                    const points = [[0.5, 0.5], [0.25, 0.5], [0.75, 0.5], [0.5, 0.25], [0.5, 0.75], [0.15, 0.15], [0.85, 0.85]];
                    let first = null;
                    for (const [fx, fy] of points) {
                        const x = r.left + r.width * fx, y = r.top + r.height * fy;
                        const top = document.elementFromPoint(x, y); if (!top) continue;
                        if (el === top || el.contains(top) || top.contains(el)) {
                            return (fx === 0.5 && fy === 0.5) ? null : {x: r.width * fx, y: r.height * fy};
                        }
                        if (first === null) first = top;
                    }
                    if (first === null) return "hidden";
                    let node = first;
                    while (node && !window.__broEls.includes(node)) node = node.parentElement;
                    return node ? "ref:" + window.__broEls.indexOf(node) : "other:" + (first.tagName || "?").toLowerCase();
                }""",
                element.ref,
            )
        except Exception:
            return None
        return hit

    async def _type_into(self, page: Page, locator, element: Element, text: str) -> str:
        """Select-all and retype; the last character goes as a real key so autocompletes and date pickers react."""
        if element.tag == "select":
            try:
                await locator.select_option(label=text, timeout=3000)
            except Exception:
                await locator.select_option(value=text, timeout=3000)
            return "ok"
        if element.attrs.get("type") in ("date", "time", "datetime-local", "month", "week"):
            await locator.evaluate(
                "(el, v) => { const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value'); d.set.call(el, v); el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
                text,
            )
            return "ok"
        await locator.click(timeout=3000)
        await page.keyboard.press("Meta+A")
        await page.keyboard.press("Backspace")
        if len(text) > 1:
            await page.keyboard.insert_text(text[:-1])
        if text:
            await page.keyboard.press(text[-1]) if len(text[-1]) == 1 and text[-1].isprintable() and text[-1] != " " else await page.keyboard.insert_text(text[-1])
        await settle(page, quiet_ms=80, max_ms=600)
        try:
            shown = await page.evaluate("() => { const a = document.activeElement; return a && 'value' in a ? String(a.value).slice(0, 60) : '' }")
        except Exception:
            shown = ""
        if shown and shown.strip() != text.strip():
            return f"ok, field now shows '{shown}'"
        return "ok"

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
        # The page changed, but only back to a state already seen. Only an identical action that
        # bounces the page back counts as a no-op (open/close toggling); otherwise it is just information.
        if self._last_action is not None and self._last_action == self._current_action:
            if element is not None:
                self._noop[element.fingerprint()] = self._noop.get(element.fingerprint(), 0) + 1
            return "ok, but this only toggled the page back to a state you had already seen (no progress)"
        self._step_effect = True
        return "ok (a page state seen before)"

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
            if action.name == "read":
                try:
                    text = await page.evaluate("() => (document.querySelector('main, [role=main]') || document.body).innerText.replace(/\\s+/g, ' ').trim().slice(0, 3000)")
                except Exception as exc:
                    return f"error: {str(exc)[:80]}"
                return f"page text: {text}"
            if action.name == "find":
                found = await page.evaluate(
                    """(needle) => { const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); const n = needle.toLowerCase();
                        while (walker.nextNode()) { const t = walker.currentNode; if (t.textContent.toLowerCase().includes(n) && t.parentElement) {
                            const cs = getComputedStyle(t.parentElement); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                            t.parentElement.scrollIntoView({block: 'center'}); return true; } } return false; }""",
                    action.text,
                )
                await settle(page, quiet_ms=80, max_ms=600)
                if not found:
                    return f"error: '{action.text[:40]}' is not on this page"
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
                before = await self._control_state(locator) if self._is_control(element) else None
                blocker = await self._covered_by(page, element) if element.ref is not None else None
                if blocker == "disabled":
                    return self._refuse(element, "error: that element is disabled; nothing was clicked")
                if blocker in ("hidden", "gone"):
                    return self._refuse(element, "error: that element is not visible; nothing was clicked")
                if isinstance(blocker, str) and blocker.startswith("ref:"):
                    cover = next((e for e in obs.elements if e.ref == int(blocker[4:]) and e.frame_url == element.frame_url), None)
                    passive = cover is not None and cover.tag in ("span", "div", "p", "li", "img", "label") and not cover.attrs.get("href") and not cover.attrs.get("role")
                    if cover is not None and cover is not element and not passive:
                        return self._refuse(element, f"error: covered by [{cover.index}]<{cover.tag}>{cover.text[:40]}; nothing was clicked (dismiss or use that first)")
                    if passive:
                        # A badge or wrapper lies over the target: click where a user would, the event bubbles to the target.
                        box = await locator.bounding_box()
                        if box:
                            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            await settle(page)
                            return await self._with_state(locator, before, await self._after(page, obs, element))
                try:
                    if isinstance(blocker, dict):
                        await locator.click(position={"x": blocker["x"], "y": blocker["y"]}, timeout=3000)
                    else:
                        await locator.click(timeout=3000)
                except Exception:
                    box = await locator.bounding_box()
                    if not box:
                        return "error: element is not visible; nothing was clicked"
                    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await settle(page)
                return await self._with_state(locator, before, await self._after(page, obs, element))
            if action.name == "type":
                outcome = await self._type_into(page, locator, element, action.text)
                self._step_effect = True
                return outcome
            if action.name == "select":
                try:
                    await locator.select_option(label=action.text, timeout=3000)
                except Exception:
                    await locator.select_option(value=action.text, timeout=3000)
                await settle(page)
                outcome = await self._after(page, obs, element)
                try:
                    shown = await locator.evaluate("el => el.selectedOptions && el.selectedOptions.length ? el.selectedOptions[0].textContent.trim() : ''")
                except Exception:
                    shown = ""
                return f"{outcome} (dropdown now shows {shown[:60]!r})" if shown else outcome
            return f"error: unknown action {action.name}"
        except Exception as exc:
            message = str(exc).splitlines()[0][:120]
            return f"error: {message}"
