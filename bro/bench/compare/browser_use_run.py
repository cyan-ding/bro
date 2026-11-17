"""Run browser-use 1.0.3 on Emergence WebVoyager tasks, each on a fresh headless Chrome and profile (its default setup).

Runs in the browser-use environment from the repo root, with PYTHONPATH=. :

    # benchmark: no recording, resumable, stops starting tasks after --deadline (epoch seconds)
    .venv-browser-use/bin/python -m bro.bench.compare.browser_use_run bench \
        --tasks bro/bench/tasks_emergence_150.json --out bu_results.jsonl
    # one recorded task (the recorder runs in Bro's environment)
    .venv-browser-use/bin/python -m bro.bench.compare.browser_use_run record EWV-001-Allrecipes out/EWV-001-Allrecipes/bu

Chrome gets the normal Chrome user-agent, the same as Bro's headless mode.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

from browser_use import Agent, Browser, ChatOpenAI  # noqa: E402

from .models import CHROME, BrowserUseRecord, RecordedRun, TaskSpec, load_task_specs  # noqa: E402

PORT = 9333
MAX_STEPS = 25
TIMEOUT_S = 240


def chrome_user_agent() -> str:
    major = subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.split()[-1].split(".")[0]
    return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"


def launch_chrome(profile: Path) -> subprocess.Popen:
    args = [CHROME, f"--user-data-dir={profile}", f"--remote-debugging-port={PORT}", "--headless=new", "--window-size=1440,1100",
            f"--user-agent={chrome_user_agent()}", "--no-first-run", "--no-default-browser-check", "about:blank"]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_chrome(chrome: subprocess.Popen, profile: Path) -> None:
    chrome.terminate()
    try:
        chrome.wait(timeout=10)
    except subprocess.TimeoutExpired:
        chrome.kill()
    shutil.rmtree(profile, ignore_errors=True)


def make_agent(task: TaskSpec, model: str, base_url: str, api_key: str) -> Agent:
    llm = ChatOpenAI(model, base_url=base_url, api_key=api_key)
    return Agent(f"Start at {task.url}. {task.task}", llm=llm, browser=Browser(cdp_url=f"http://127.0.0.1:{PORT}"))


async def bench_one(task: TaskSpec, model: str, base_url: str, api_key: str) -> BrowserUseRecord:
    profile = Path(tempfile.mkdtemp(prefix="bu-profile-"))
    chrome = launch_chrome(profile)
    await asyncio.sleep(2.5)
    started = time.time()
    record = BrowserUseRecord(task_id=task.id, agent="browser-use 1.0.3", model=model, total_s=0)
    try:
        result = await asyncio.wait_for(make_agent(task, model, base_url, api_key).run(max_steps=MAX_STEPS, timeout=TIMEOUT_S), TIMEOUT_S + 90)
        record.answer, record.steps, record.status, record.error = result.final_result(), result.steps, result.status, result.error
        record.usage = dict(result.usage)
    except Exception as exc:
        record.error = f"{type(exc).__name__}: {exc}"[:300]
    record.total_s = round(time.time() - started, 1)
    stop_chrome(chrome, profile)
    return record


async def bench(tasks_path: Path, out: Path, model: str, base_url: str, api_key: str, deadline: Optional[float]) -> None:
    done = {json.loads(line)["task_id"] for line in out.read_text().splitlines() if line.strip()} if out.exists() else set()
    for task in load_task_specs(tasks_path).values():
        if task.id in done:
            continue
        if deadline and time.time() > deadline:
            print("deadline reached", flush=True)
            return
        record = await bench_one(task, model, base_url, api_key)
        with out.open("a") as handle:
            handle.write(record.model_dump_json() + "\n")
        print(f"{time.strftime('%H:%M:%S')} {task.id} {record.total_s}s steps={record.steps} | {(record.answer or record.error or '')[:80]}", flush=True)


async def record_one(task: TaskSpec, out: Path, model: str, base_url: str, api_key: str, bro_python: str) -> RecordedRun:
    profile = Path(tempfile.mkdtemp(prefix="bu-profile-"))
    chrome = launch_chrome(profile)
    await asyncio.sleep(2.5)
    recorder = subprocess.Popen([bro_python, "-m", "bro.bench.compare.screencast", "--cdp", f"http://127.0.0.1:{PORT}", "--out", str(out / "frames")])
    await asyncio.sleep(2)
    started = time.time()
    run = RecordedRun(agent="browser-use 1.0.3", model=model, task_id=task.id, elapsed_s=0)
    try:
        result = await make_agent(task, model, base_url, api_key).run(max_steps=MAX_STEPS, timeout=TIMEOUT_S)
        run.answer, run.steps, run.cost_usd = result.final_result(), result.steps, result.cost_usd
    except Exception as exc:
        run.error = f"{type(exc).__name__}: {exc}"[:200]
    run.elapsed_s = round(time.time() - started, 1)
    recorder.terminate()
    recorder.wait(timeout=30)
    stop_chrome(chrome, profile)
    (out / "result.json").write_text(run.model_dump_json(indent=1))
    return run


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["bench", "record"])
    parser.add_argument("task_id", nargs="?", help="record mode: task id")
    parser.add_argument("out_dir", nargs="?", help="record mode: output directory")
    parser.add_argument("--tasks", default="bro/bench/tasks_emergence.json")
    parser.add_argument("--out", default="bu_results.jsonl", help="bench mode: results file")
    parser.add_argument("--model", default="mlx-community/Qwen3.6-35B-A3B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--api-key", default=os.environ.get("BU_API_KEY", "local"))
    parser.add_argument("--deadline", type=float, help="bench mode: epoch seconds after which no new task starts")
    parser.add_argument("--bro-python", default=".venv/bin/python", help="record mode: Python of Bro's environment")
    args = parser.parse_args()
    if args.mode == "bench":
        asyncio.run(bench(Path(args.tasks), Path(args.out), args.model, args.base_url, args.api_key, args.deadline))
    else:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        spec = load_task_specs(Path(args.tasks))[args.task_id]
        done = asyncio.run(record_one(spec, out_dir, args.model, args.base_url, args.api_key, args.bro_python))
        print(done.task_id, "browser-use", done.elapsed_s, "s", done.steps, "steps |", (done.answer or done.error or "")[:80])
