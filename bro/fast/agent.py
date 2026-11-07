"""The fast agent loop: observe (text only) -> one short LLM call -> act -> settle."""

import asyncio
import time
from typing import Awaitable, Callable, List, Optional, Tuple
from urllib.parse import quote_plus

from patchright.async_api import BrowserContext, Page
from pydantic import BaseModel, Field

from .dsl import Action, parse
from .llm import ChatModel, Completion
from .observe import Element, Observation, format_elements, observe, observe_lean
from .prompts import FINAL_STEP_SUFFIX, USER_TEMPLATE, VERIFY_SUFFIX, system_prompt
from .settle import settle

PAGE_CHANGING = {"click", "goto", "search", "back", "press", "scroll", "select"}
ALWAYS_RUN = {"done"}
MAX_ACTIONS_PER_STEP = 3
MAX_VETOES = 2


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


class RunResult(BaseModel):
    task: str
    model: str
    answer: Optional[str] = None
    finished: bool = False
    error: Optional[str] = None
    steps: List[StepRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    total_ms: int = 0


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
        observer: str = "lean",
    ):
        self.observer = observer
        self.verify = verify
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
                obs = await self._observe(page)
                record.observe_ms = int((time.perf_counter() - observe_started) * 1000)

                user_prompt = self._build_user_prompt(task, obs)
                if step == max_steps:
                    user_prompt += FINAL_STEP_SUFFIX
                record.prompt_chars = len(self.system) + len(user_prompt)
                completion = await self._complete(user_prompt)
                record.output = completion.text
                record.llm_ms = completion.latency_ms
                record.prompt_tokens = completion.prompt_tokens
                record.cached_tokens = completion.cached_tokens
                record.completion_tokens = completion.completion_tokens

                actions = parse(completion.text)
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
                        if veto:
                            self.history.append(f"{step}. (self-check rejected the answer: {veto}; keep working)")
                            break
                        result.answer = action.text
                        result.finished = True
                        break
                    if outcome.startswith("error") or action.name in PAGE_CHANGING:
                        page_changed = True
                record.act_ms = int((time.perf_counter() - act_started) * 1000)
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
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await settle(page)

    def _locator(self, page: Page, element: Element):
        if element.iframe_xpath:
            return page.frame_locator(f"xpath={element.iframe_xpath}").locator(f"xpath={element.xpath}")
        return page.locator(f"xpath={element.xpath}")

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
                return f"ok, now at {await page.title()}"
            if action.name == "search":
                await self._goto(page, f"https://www.google.com/search?q={quote_plus(action.text)}")
                return f"ok, now at {await page.title()}"
            if action.name == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
                await settle(page)
                return f"ok, now at {await page.title()}"
            if action.name == "press":
                await page.keyboard.press(action.text or "Enter")
                await settle(page)
                return f"ok, now at {await page.title()}"
            if action.name == "scroll":
                sign = -1 if action.text == "up" else 1
                await page.evaluate(f"window.scrollBy(0, {sign} * window.innerHeight * 0.8)")
                await settle(page, quiet_ms=100, max_ms=600)
                return "ok"
            element = obs.element(action.index or -1)
            if element is None:
                return f"error: no element with index {action.index}"
            locator = await self._target(page, element)
            if locator is None:
                return "error: element is no longer on the page"
            if action.name == "click":
                before = page.url
                try:
                    await locator.click(timeout=3000)
                except Exception:
                    await locator.evaluate("el => el.click()")
                await settle(page)
                changed = page.url != before
                return f"ok, now at {await page.title()}" if changed else "ok"
            if action.name == "type":
                try:
                    await locator.fill(action.text, timeout=3000)
                except Exception:
                    await locator.click(timeout=2000)
                    await page.keyboard.press("Meta+A")
                    await page.keyboard.type(action.text)
                await settle(page, quiet_ms=100, max_ms=600)
                return "ok"
            if action.name == "select":
                try:
                    await locator.select_option(label=action.text, timeout=3000)
                except Exception:
                    await locator.select_option(value=action.text, timeout=3000)
                await settle(page)
                return "ok"
            return f"error: unknown action {action.name}"
        except Exception as exc:
            message = str(exc).splitlines()[0][:120]
            return f"error: {message}"
