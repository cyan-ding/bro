"""Judge browser-use answers with Bro's benchmark judge, then compare both agents on the same tasks, speed first.

    python -m bro.bench.compare.score compare bu_results.jsonl bro/bench/results/full_headless.jsonl
    python -m bro.bench.compare.score recording out/EWV-001-Allrecipes      # judge a recorded pair (bro/, bu/)
"""

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from typing import Callable, Dict, List

from pydantic import BaseModel

from bro.bench.judge import Task, judge
from bro.bench.run import BenchRecord

from .models import BrowserUseRecord, RecordedRun


class Judged(BaseModel):
    success: bool
    reason: str


def load_tasks(path: Path) -> Dict[str, Task]:
    return {t["id"]: Task(**t) for t in json.loads(path.read_text())}


def load_lines(path: Path, model: Callable[..., BaseModel]) -> List[BaseModel]:
    return [model(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


async def judge_all(records: List[BrowserUseRecord], tasks: Dict[str, Task], cache_path: Path) -> Dict[str, Judged]:
    cache = {k: Judged(**v) for k, v in json.loads(cache_path.read_text()).items()} if cache_path.exists() else {}
    for record in records:
        if record.task_id not in cache:
            verdict = await judge(tasks[record.task_id], record.answer or "")
            cache[record.task_id] = Judged(success=verdict.success, reason=verdict.reason)
            cache_path.write_text(json.dumps({k: v.model_dump() for k, v in cache.items()}))
    return cache


def summary(name: str, ids: List[str], ok: Dict[str, bool], seconds: Dict[str, float]) -> None:
    solved = [seconds[t] for t in ids if ok[t]]
    within = [sum(1 for t in ids if ok[t] and seconds[t] <= limit) for limit in (30, 60, 120)]
    print(f"{name:20s} solved {sum(ok[t] for t in ids):3d}/{len(ids)}  median {statistics.median(seconds[t] for t in ids):6.1f}s  "
          f"median on solved {statistics.median(solved) if solved else 0:6.1f}s  within 30/60/120 s {within}  "
          f"total {sum(seconds[t] for t in ids) / 3600:.2f} h")


async def compare(bu_path: Path, bro_path: Path, tasks_path: Path) -> None:
    tasks = load_tasks(tasks_path)
    bu = {r.task_id: r for r in load_lines(bu_path, BrowserUseRecord)}
    bro = {r.task_id: r for r in load_lines(bro_path, BenchRecord)}
    verdicts = await judge_all(list(bu.values()), tasks, bu_path.with_suffix(".judged.json"))
    ids = [t for t in bu if t in bro]
    ok_bro, sec_bro = {t: bro[t].success for t in ids}, {t: bro[t].total_s for t in ids}
    ok_bu, sec_bu = {t: verdicts[t].success for t in ids}, {t: bu[t].total_s for t in ids}
    print(f"{len(ids)} tasks in both runs")
    summary("Bro", ids, ok_bro, sec_bro)
    summary("browser-use", ids, ok_bu, sec_bu)
    both = [t for t in ids if ok_bro[t] and ok_bu[t]]
    if both:
        ratio = statistics.median(sec_bu[t] / sec_bro[t] for t in both)
        print(f"solved by both: {len(both)}, median time ratio browser-use / Bro {ratio:.1f}x")
    print(f"solved only by Bro {sum(ok_bro[t] and not ok_bu[t] for t in ids)}, only by browser-use {sum(ok_bu[t] and not ok_bro[t] for t in ids)}")
    for site in sorted({t.split("-")[-1] for t in ids}):
        st = [t for t in ids if t.endswith(site)]
        print(f"   {site:20s} Bro {sum(ok_bro[t] for t in st)}/{len(st)} {statistics.median(sec_bro[t] for t in st):6.1f}s"
              f"   browser-use {sum(ok_bu[t] for t in st)}/{len(st)} {statistics.median(sec_bu[t] for t in st):6.1f}s")


async def judge_recording(task_dir: Path, tasks_path: Path) -> None:
    task = load_tasks(tasks_path)[task_dir.name]
    for side in ("bro", "bu"):
        path = task_dir / side / "result.json"
        run = RecordedRun(**json.loads(path.read_text()))
        verdict = await judge(task, run.answer or "")
        run.success, run.judge = verdict.success, verdict.reason
        path.write_text(run.model_dump_json(indent=1))
        print(task.id, side, run.elapsed_s, "s", "PASS" if run.success else "FAIL")
    (task_dir / "task.txt").write_text(task.task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    cmp_parser = sub.add_parser("compare")
    cmp_parser.add_argument("browser_use_results")
    cmp_parser.add_argument("bro_results")
    rec_parser = sub.add_parser("recording")
    rec_parser.add_argument("task_dir")
    parser.add_argument("--tasks", default="bro/bench/tasks_emergence.json")
    args = parser.parse_args()
    if args.mode == "compare":
        asyncio.run(compare(Path(args.browser_use_results), Path(args.bro_results), Path(args.tasks)))
    else:
        asyncio.run(judge_recording(Path(args.task_dir), Path(args.tasks)))
