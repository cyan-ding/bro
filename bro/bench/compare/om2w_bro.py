"""Run one Online-Mind2Web task with Bro (headless, local model), record it, and write the WebJudge trajectory:
OUT/<task_id>/bro/result.json + trajectory/N.jpg.

    uv run python -m bro.bench.compare.om2w_bro TASK_ID bro/bench/results/om2w/Online_Mind2Web.json OUT
"""

import argparse
import asyncio
import os
import re
import time
from pathlib import Path
from typing import List

from bro.fast.agent import FastAgent, StepRecord
from bro.fast.browser import connect, disconnect, fresh_page
from bro.fast.observe import Observation

from .models import Om2wResult, load_om2w_tasks, write_trajectory
from .screencast import Screencast

MODEL = os.environ.get("BRO_MODEL", "local/mlx-community/Qwen3.6-35B-A3B-4bit")
TIMEOUT_S = 240


def describe(action: str, obs: Observation) -> str:
    """'click 12' -> 'click 12 (<a> Store locator)' so the judge can read what was acted on."""
    match = re.match(r"(\w+)\s+(\d+)", action)
    element = obs.element(int(match.group(2))) if match else None
    if element is None:
        return action
    label = element.text or element.attrs.get("aria-label") or element.attrs.get("placeholder") or element.attrs.get("href") or ""
    return f"{action} (<{element.tag}> {label[:60]})"


async def run(task_id: str, tasks_path: Path, out: Path) -> Om2wResult:
    task = load_om2w_tasks(tasks_path)[task_id]
    side = out / task_id / "bro"
    side.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("BRO_BROWSER", "patchright")
    os.environ.setdefault("BRO_HEADLESS", "1")
    playwright, browser, context = await connect()
    await context.clear_cookies()
    page = await fresh_page(context)
    recorder = Screencast(side / "frames")
    await recorder.attach(context)
    actions: List[str] = []

    async def on_step(record: StepRecord, obs: Observation) -> None:
        actions.extend(describe(a, obs) for a in record.actions)

    agent = FastAgent(MODEL, time_budget_s=TIMEOUT_S * 0.85, on_step=on_step)
    started = time.time()
    answer, error, steps = "", None, None
    try:
        result = await asyncio.wait_for(agent.run(context, page, task.task, task.url, 25), TIMEOUT_S)
        answer, error, steps = result.answer or "", result.error, len(result.steps)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:200]
    elapsed = round(time.time() - started, 1)
    await recorder.stop()
    await disconnect(playwright, browser, context)
    write_trajectory(side / "frames", side, len(actions))
    record = Om2wResult(task_id=task_id, task=task.task, action_history=actions, final_result_response=answer,
                        agent="bro", model=MODEL, steps=steps, elapsed_s=elapsed, error=error)
    (side / "result.json").write_text(record.model_dump_json(indent=1))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("tasks")
    parser.add_argument("out")
    args = parser.parse_args()
    done = asyncio.run(run(args.task_id, Path(args.tasks), Path(args.out)))
    print(f"{time.strftime('%H:%M:%S')} {done.task_id[:12]} bro {done.elapsed_s}s steps={done.steps} | {(done.final_result_response or done.error or '')[:80]}", flush=True)
