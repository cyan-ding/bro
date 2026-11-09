"""Summarize an offline System 1 replay: agreement with the planner at each confidence threshold.

`python -m bro.bench.calib calib.jsonl`
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]


def main() -> None:
    rows = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
    by_model: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        if "skipped" in row:
            print(f"skipped {row['s1']}: {row['skipped']}")
            continue
        by_model[row["s1"]].append(row)
    print("| System 1 | states | ms/decision | agree (all) | agree (planner clicked/scrolled) | " + " | ".join(f"act@{t} acc/cov" for t in THRESHOLDS[1:]) + " |")
    print("|---|---|---|---|---|" + "---|" * len(THRESHOLDS[1:]))
    for model, items in by_model.items():
        n = len(items)
        ms = sum(r["latency_ms"] for r in items) / n
        agree = sum(r["agrees"] for r in items) / n
        actionable = [r for r in items if r["ideal_is_action"]]
        agree_act = sum(r["agrees"] for r in actionable) / max(1, len(actionable))
        cells = []
        for t in THRESHOLDS[1:]:
            acting = [r for r in items if not r["escalate"] and r["confidence"] >= t]
            acc = sum(r["agrees"] for r in acting) / max(1, len(acting))
            cells.append(f"{acc:.0%} / {len(acting) / n:.0%}")
        print(f"| {model.split('/')[-1]} | {n} | {ms:.0f} | {agree:.0%} | {agree_act:.0%} ({len(actionable)}) | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
