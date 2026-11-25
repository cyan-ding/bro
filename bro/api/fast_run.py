"""Adapter that runs the fast loop behind the same interface the API uses for the legacy Agent."""

import asyncio
from typing import List, Optional, Tuple

from agent.agent_state import AgentState
from agent.models import StructuredOutputContext, TabState
from utils.db import save_run_state
from utils.input_manager import InputManager

from bro.fast.agent import FastAgent, StepRecord
from bro.fast.browser import connect
from bro.fast.local_server import ensure_local_server
from bro.fast.dsl import parse
from bro.fast.observe import Element, Observation

from .models import LogType, RunStatus
from .run_info import RunInfo


def _element_label(element: Element) -> str:
    for candidate in (element.text, element.attrs.get("aria-label"), element.attrs.get("placeholder"), element.attrs.get("title"), element.attrs.get("alt")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:60]
    return ""


def describe_action(command: str, outcome: str, obs: Observation) -> str:
    """Plain-language step, naming the element from the observation the action was planned on."""
    parsed = parse(command)
    if not parsed:
        return command
    action = parsed[0]
    element = next((e for e in obs.elements if e.index == action.index), None) if action.index is not None else None
    label = _element_label(element) if element else ""
    target = f'"{label}"' if label else (f"a {element.tag}" if element else "something")
    arrived = outcome.split("now at ", 1)[1].strip() if "now at " in outcome else ""
    if action.name == "click":
        text = f"Clicked {target}"
    elif action.name == "type":
        text = f'Typed "{action.text}" into {target}'
    elif action.name == "select":
        text = f'Picked "{action.text}" in {target}'
    else:
        return command
    return f"{text} → {arrived}" if arrived else text


class FastRun:
    def __init__(self, model: str, run_info: RunInfo):
        self.model = model
        self.run_info = run_info
        self.agent_state = AgentState()
        self.input_manager: Optional[InputManager] = None
        self.agent = FastAgent(
            model,
            on_step=self._on_step,
            on_done=self._on_done,
            get_messages=self._messages,
            wait_for_user=self._wait_for_user,
        )

    async def run(self, user_prompt: str, url: str = "", max_iterations: int = 100, enable_input_queue: bool = True) -> None:
        self.agent_state.max_iterations = max_iterations
        if enable_input_queue:
            self.input_manager = InputManager(enable_stdin=False)
            await self.input_manager.start()
        await asyncio.to_thread(ensure_local_server, self.model)
        playwright, browser, context = await connect()
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await self.agent.run(context, page, user_prompt, url or None, max_iterations)
        finally:
            await browser.close()
            await playwright.stop()
            if self.input_manager:
                await self.input_manager.stop()

    def _messages(self) -> List[str]:
        return self.input_manager.get_messages() if self.input_manager else []

    async def _wait_for_user(self) -> bool:
        return await self.input_manager.wait_while_driving() if self.input_manager else False

    async def _on_step(self, record: StepRecord, obs: Observation) -> None:
        comments = [line.lstrip("# ") for line in record.output.splitlines() if line.strip().startswith("#")]
        thinking = StructuredOutputContext(
            thinking=" ".join(comments),
            evaluation_previous_actions="",
            memory="; ".join(self.agent.notes),
            next_goal="\n".join(record.actions),
        )
        await self.run_info.add_log_event(LogType.THINKING, thinking_context=thinking)
        for command, outcome in zip(record.actions, record.results):
            await self.agent_state.add_action_context(
                action_name=command.split()[0],
                arguments={"command": command},
                result=outcome,
                iteration=record.step,
                description=describe_action(command, outcome, obs),
                logger=self.run_info.add_log_event,
            )
        self.agent_state.tabs = [TabState(url=obs.url, title=obs.title, is_active=True)]
        self.agent_state.current_tab_index = 0
        self.run_info.update_iteration()
        await save_run_state(self.run_info)

    async def _on_done(self, answer: str) -> Tuple[str, str]:
        if not self.input_manager:
            return "done", ""
        self.run_info.set_status(RunStatus.AWAITING_DECISION)
        await save_run_state(self.run_info)
        while True:
            choice = (await self.input_manager.get_decision()).strip().upper()
            if choice in ("D", "DONE"):
                return "done", ""
            if choice in ("M", "MODIFY"):
                extra = (await self.input_manager.get_decision()).strip()
                if not extra:
                    continue
                self.run_info.set_status(RunStatus.RUNNING)
                await save_run_state(self.run_info)
                return "modify", extra
            if choice in ("I", "INTERVENE"):
                await self.input_manager.get_decision()
                self.run_info.set_status(RunStatus.RUNNING)
                await save_run_state(self.run_info)
                return "intervene", ""
