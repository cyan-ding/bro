"""Run the demo task queue with Bro in headless Chrome on the local model, record the invisible browser, post a macOS
notification as each task finishes, and log focus and memory every second to OUT/timeline.json.

    uv run python -m bro.demo.run bro/demo/tasks.json demo-runs/take-1

Expects the local model on BRO_LOCAL_BASE_URL (bro/demo/start.sh starts it).
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Set

os.environ.setdefault("BRO_BROWSER", "patchright")
os.environ.setdefault("BRO_HEADLESS", "1")
os.environ.setdefault("BRO_LOCAL_EXTERNAL", "1")

from bro.bench.compare.screencast import Screencast  # noqa: E402
from bro.fast.agent import FastAgent  # noqa: E402
from bro.fast.browser import _frontmost, connect, disconnect, fresh_page  # noqa: E402

from .models import DemoTask, Sample, TaskResult, Timeline  # noqa: E402

MODEL = "local/mlx-community/Qwen3.6-35B-A3B-4bit"
TIMEOUT_S = 240


def agent_chrome_pids() -> Set[int]:
    profile = os.environ.get("BRO_PROFILE_DIR", os.path.expanduser("~/tmp/chrome-profile-patchright-headless"))
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    return {int(line.split()[0]) for line in out.splitlines() if f"--user-data-dir={profile}" in line}


def free_pct() -> int:
    out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)%", out)
    return int(match.group(1)) if match else -1


def notify(title: str, body: str) -> None:
    """A macOS notification; it never takes focus from the app you are using."""
    body = body.replace('"', "'").replace("\\", " ")[:180]
    subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'], capture_output=True)


async def sample_every_second(timeline: Timeline, stop: asyncio.Event) -> None:
    pids = agent_chrome_pids()
    while not stop.is_set():
        name, pid = await asyncio.to_thread(_frontmost)
        if len(timeline.samples) % 10 == 0:
            pids = agent_chrome_pids()
        t = round(time.time() - timeline.start_epoch, 2)
        timeline.samples.append(Sample(t=t, front=name, agent_front=pid in pids, free_pct=free_pct()))
        await asyncio.sleep(1)


async def run(tasks_path: Path, out: Path) -> None:
    tasks = [DemoTask(**t) for t in json.loads(tasks_path.read_text())]
    out.mkdir(parents=True, exist_ok=True)
    playwright, browser, context = await connect()
    timeline = Timeline(start_epoch=time.time())
    recorder = Screencast(out / "frames")
    recorder.t0 = timeline.start_epoch
    await fresh_page(context)
    await recorder.attach(context)
    stop = asyncio.Event()
    sampler = asyncio.create_task(sample_every_second(timeline, stop))
    notify("Bro", f"Starting {len(tasks)} tasks in the background")
    for task in tasks:
        await context.clear_cookies()
        page = await fresh_page(context)
        result = TaskResult(id=task.id, label=task.label, start=round(time.time() - timeline.start_epoch, 1))
        try:
            agent = FastAgent(MODEL, time_budget_s=TIMEOUT_S * 0.85)
            run_result = await asyncio.wait_for(agent.run(context, page, task.task, task.url, 25), TIMEOUT_S)
            result.answer, result.steps, result.error = run_result.answer, len(run_result.steps), run_result.error
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"[:200]
        result.end = round(time.time() - timeline.start_epoch, 1)
        timeline.tasks.append(result)
        took = result.end - result.start
        notify(f"Bro: {task.label} ({took:.0f} s)", result.answer or result.error or "no answer")
        print(f"{result.end:7.1f}s  {task.label:32s} {took:5.1f}s | {(result.answer or result.error or '')[:90]}", flush=True)
        (out / "timeline.json").write_text(timeline.model_dump_json(indent=1))
    stop.set()
    await sampler
    await recorder.stop()
    await disconnect(playwright, browser, context)
    timeline.end = round(time.time() - timeline.start_epoch, 1)
    (out / "timeline.json").write_text(timeline.model_dump_json(indent=1))
    notify("Bro", f"All {len(tasks)} tasks done in {timeline.end:.0f} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks")
    parser.add_argument("out")
    args = parser.parse_args()
    asyncio.run(run(Path(args.tasks), Path(args.out)))
