"""Run the original Bro agent loop headlessly so it can be benchmarked."""

import time
from pathlib import Path
from typing import Optional, Tuple

from bro.agent.agent import Agent
from bro.api.run_info import RunInfo
from bro.fast.agent import RunResult, StepRecord


class _AutoDoneAgent(Agent):
    """Original agent, but `done` ends the run instead of waiting for the user."""

    async def _handle_user_decision(self, reason: str, input_manager=None) -> Tuple[str, str]:
        return "done", ""


async def run_legacy(model: str, task: str, url: Optional[str], max_steps: int) -> RunResult:
    system_prompt = (Path(__file__).parent.parent.parent / "bro.txt").read_text(encoding="utf-8")
    run_info = RunInfo(run_id="bench", agent=None, max_iterations=max_steps, user_prompt=task)
    agent = _AutoDoneAgent(system_prompt, model=model, run_info=run_info)
    run_info.agent = agent
    started = time.perf_counter()
    result = RunResult(task=task, model=model)
    try:
        await agent.run(user_prompt=task, url=url or "", max_iterations=max_steps, enable_input_queue=False)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    result.total_ms = int((time.perf_counter() - started) * 1000)
    history = agent.agent_state.action_history
    for action in history:
        result.steps.append(
            StepRecord(step=action.iteration, url="", output=action.description or "", actions=[action.action_name], results=[action.result[:200]])
        )
    done = next((a for a in history if a.action_name == "done"), None)
    if done:
        result.answer = str(done.arguments.get("reason", ""))
        result.finished = True
    return result
