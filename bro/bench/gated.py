"""Summarize gated System 1/2 runs: `python -m bro.bench.gated results/*.jsonl`."""

import json
import os
import statistics as st
import sys
from pathlib import Path


def main() -> None:
    exclude = os.environ.get("BENCH_EXCLUDE", "")
    print("| run | pass | median s | mean s | steps | S1 share | S1 ms | S2 ms | s/step |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in sys.argv[1:]:
        rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        rows = [r for r in rows if not exclude or not r["task_id"].startswith(exclude)]
        if not rows:
            continue
        steps = [s for r in rows for s in r["result"]["steps"]]
        s1 = [s for s in steps if s.get("system") == "s1"]
        s2 = [s for s in steps if s.get("system") != "s1"]
        total = sum(r["total_s"] for r in rows)
        print(
            f"| {os.path.basename(path)[:-6]} | {sum(r['success'] for r in rows)}/{len(rows)} | "
            f"{st.median(r['total_s'] for r in rows):.1f} | {st.mean(r['total_s'] for r in rows):.1f} | {len(steps)} | "
            f"{len(s1) / max(1, len(steps)):.0%} | {st.mean(s['llm_ms'] for s in s1) if s1 else 0:.0f} | "
            f"{st.mean(s['llm_ms'] for s in s2) if s2 else 0:.0f} | {total / max(1, len(steps)):.2f} |"
        )


if __name__ == "__main__":
    main()
