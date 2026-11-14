"""Paired comparison of runs on the tasks they all completed: `python -m bro.bench.paired a.jsonl b.jsonl ...`."""

import collections
import json
import os
import statistics as st
import sys
from pathlib import Path


def main() -> None:
    runs = {os.path.basename(p)[:-6]: {r["task_id"]: r for r in map(json.loads, Path(p).read_text().splitlines()) if r} for p in sys.argv[1:]}
    ids = sorted(set.intersection(*(set(v) for v in runs.values())))
    names = list(runs)
    print(f"{len(ids)} tasks completed by every run\n")
    print("| run | pass | median s | steps median | failed at cap | vision steps |")
    print("|---|---|---|---|---|---|")
    for name in names:
        rows = [runs[name][i] for i in ids]
        ok = sum(r["success"] for r in rows)
        times = [r["total_s"] for r in rows if r["steps"] > 0]
        vision = sum(1 for r in rows for s in r["result"]["steps"] if s.get("vision"))
        print(f"| {name} | {ok}/{len(ids)} ({100 * ok / len(ids):.1f}%) | {st.median(times):.0f} | {st.median(r['steps'] for r in rows):.0f} | {sum(1 for r in rows if not r['success'] and r['steps'] >= 25)} | {vision} |")
    print("\n| site | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    by = collections.defaultdict(lambda: [0] + [0] * len(names))
    for i in ids:
        site = i.split("-")[-1]
        by[site][0] += 1
        for k, name in enumerate(names):
            by[site][k + 1] += runs[name][i]["success"]
    for site, counts in sorted(by.items(), key=lambda kv: -kv[1][-1]):
        print(f"| {site} | " + " | ".join(f"{c}/{counts[0]}" for c in counts[1:]) + " |")
    first, last = names[0], names[-1]
    up = sum(1 for i in ids if not runs[first][i]["success"] and runs[last][i]["success"])
    down = sum(1 for i in ids if runs[first][i]["success"] and not runs[last][i]["success"])
    print(f"\n{last} vs {first}: {up} up, {down} down")


if __name__ == "__main__":
    main()
