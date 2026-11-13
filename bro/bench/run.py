"""Benchmark runner: `python -m bro.bench.run --agent fast --model local/... --out results.jsonl`."""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from bro.fast.agent import FastAgent, RunResult
from bro.fast.browser import connect, disconnect, fresh_page
from bro.fast.local_server import server_for, shutdown_servers
from bro.fast.system1 import make_system1
from bro.utils.env_loader import load_env_files
from bro.utils.use_cdp import use_cdp

from .judge import Task, Verdict, judge
from .legacy import run_legacy

log = logging.getLogger("bench")


class BenchRecord(BaseModel):
    task_id: str
    agent: str
    model: str
    variant: str
    success: bool
    reason: str
    answer: Optional[str]
    error: Optional[str]
    steps: int
    total_s: float
    llm_s: float
    observe_s: float
    act_s: float
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    result: RunResult


def load_tasks(path: Path, only: Optional[List[str]]) -> List[Task]:
    tasks = [Task(**t) for t in json.loads(path.read_text())]
    return [t for t in tasks if not only or t.id in only]


def summarize(result: RunResult, task: Task, agent: str, variant: str, verdict: Verdict) -> BenchRecord:
    return BenchRecord(
        task_id=task.id,
        agent=agent,
        model=result.model,
        variant=variant,
        success=verdict.success,
        reason=verdict.reason,
        answer=result.answer,
        error=result.error,
        steps=len(result.steps),
        total_s=result.total_ms / 1000,
        llm_s=sum(s.llm_ms for s in result.steps) / 1000,
        observe_s=sum(s.observe_ms for s in result.steps) / 1000,
        act_s=sum(s.act_ms for s in result.steps) / 1000,
        prompt_tokens=sum(s.prompt_tokens for s in result.steps),
        cached_tokens=sum(s.cached_tokens for s in result.steps),
        completion_tokens=sum(s.completion_tokens for s in result.steps),
        result=result,
    )


async def run_task(args: argparse.Namespace, task: Task) -> RunResult:
    """Run one task; the browser connection and teardown are inside the deadline too."""
    return await asyncio.wait_for(_run_task(args, task), args.timeout + 60)


async def _run_task(args: argparse.Namespace, task: Task) -> RunResult:
    if args.agent == "legacy":
        use_cdp()
        return await asyncio.wait_for(run_legacy(args.model, task.task, task.url, args.max_steps), args.timeout)
    playwright, browser, context = await connect()
    try:
        page = await fresh_page(context)
        agent = FastAgent(
            args.model,
            reason=args.reason,
            max_elements=args.max_elements,
            max_text_chars=args.max_text,
            verify=args.verify,
            reject_hedged_done=args.reject_hedged_done,
            observer=args.observer,
            system1=make_system1(args.s1, args.s1_threshold) if args.s1 else None,
            shadow={spec: make_system1(spec, args.s1_threshold) for spec in args.shadow},
            log_states=args.log_states,
        )
        return await asyncio.wait_for(agent.run(context, page, task.task, task.url, args.max_steps), args.timeout)
    finally:
        await disconnect(playwright, browser, context)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["fast", "legacy"], default="fast")
    parser.add_argument("--model", required=True)
    parser.add_argument("--variant", default="")
    parser.add_argument("--tasks", default=str(Path(__file__).with_name("tasks.json")))
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--reason", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--reject-hedged-done", action="store_true", help="refuse hedged non-answers while steps remain")
    parser.add_argument("--observer", choices=["lean", "legacy"], default="lean")
    parser.add_argument("--s1", help="System 1 scorer: local/<model> or jev")
    parser.add_argument("--s1-threshold", type=float, default=0.6)
    parser.add_argument("--shadow", nargs="*", default=[], help="System 1 scorers to log without acting on")
    parser.add_argument("--log-states", action="store_true", help="store each step's observation for offline replay")
    parser.add_argument("--max-elements", type=int, default=80)
    parser.add_argument("--max-text", type=int, default=800)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_env_files()
    tasks = load_tasks(Path(args.tasks), args.only)
    out = Path(args.out)
    done_ids = set()
    if out.exists():
        done_ids = {json.loads(line)["task_id"] for line in out.read_text().splitlines() if line.strip()}
    if args.model.startswith("local/"):
        server_for(args.model)
    variant = args.variant or ("reason" if args.reason else "plain")
    if args.s1 and not args.variant:
        variant = f"s1={args.s1.split('/')[-1]}@{args.s1_threshold}"
    for task in tasks:
        if task.id in done_ids:
            continue
        try:
            result = await run_task(args, task)
        except asyncio.TimeoutError:
            result = RunResult(task=task.task, model=args.model, error="timeout")
        except Exception as exc:
            result = RunResult(task=task.task, model=args.model, error=f"{type(exc).__name__}: {exc}")
        try:
            verdict = await judge(task, result.answer or "")
        except Exception as exc:
            verdict = Verdict(success=False, reason=f"judge error: {exc}")
        record = summarize(result, task, args.agent, variant, verdict)
        with out.open("a") as handle:
            handle.write(record.model_dump_json() + "\n")
        log.info(
            "%s | %s | %.1fs | %d steps | %s | %s",
            task.id,
            "PASS" if record.success else "FAIL",
            record.total_s,
            record.steps,
            (result.answer or result.error or "")[:80],
            verdict.reason,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        shutdown_servers()
