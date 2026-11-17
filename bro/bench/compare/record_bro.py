"""Run one task with Bro in headless Chrome on its own profile and record it.

python -m bro.bench.compare.record_bro EWV-001-Allrecipes local/mlx-community/Qwen3.6-35B-A3B-4bit out/EWV-001-Allrecipes/bro
"""

import argparse
import asyncio
import os
import time
from pathlib import Path

from bro.fast.agent import FastAgent
from bro.fast.browser import connect, disconnect, fresh_page

from .models import RecordedRun, load_task_specs
from .screencast import Screencast

TIMEOUT_S = 240


async def record(task_id: str, model: str, out: Path, tasks_path: Path) -> RecordedRun:
    task = load_task_specs(tasks_path)[task_id]
    os.environ.setdefault("BRO_BROWSER", "patchright")
    os.environ.setdefault("BRO_HEADLESS", "1")
    os.environ.setdefault("BRO_PROFILE_DIR", str(out.parent / "bro-profile"))
    playwright, browser, context = await connect()
    await context.clear_cookies()
    page = await fresh_page(context)
    recorder = Screencast(out / "frames")
    await recorder.attach(context)
    agent = FastAgent(model, time_budget_s=TIMEOUT_S * 0.85)
    started = time.time()
    run = RecordedRun(agent="bro", model=model, task_id=task_id, elapsed_s=0)
    try:
        result = await asyncio.wait_for(agent.run(context, page, task.task, task.url, 25), TIMEOUT_S)
        run.answer, run.error, run.steps = result.answer, result.error, len(result.steps)
    except Exception as exc:
        run.error = f"{type(exc).__name__}: {exc}"[:200]
    run.elapsed_s = round(time.time() - started, 1)
    await recorder.stop()
    await disconnect(playwright, browser, context)
    (out / "result.json").write_text(run.model_dump_json(indent=1))
    return run


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("model")
    parser.add_argument("out")
    parser.add_argument("--tasks", default="bro/bench/tasks_emergence.json")
    args = parser.parse_args()
    done = asyncio.run(record(args.task_id, args.model, Path(args.out), Path(args.tasks)))
    print(done.task_id, "bro", done.elapsed_s, "s", done.steps, "steps |", (done.answer or done.error or "")[:80])
