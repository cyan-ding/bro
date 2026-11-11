"""Join benchmark results with memory samples: `python -m bro.bench.memsweep results/mem_*.jsonl`."""

import csv
import json
import os
import statistics as st
import sys
from pathlib import Path


def main() -> None:
    print("| config | pass | median s | s/step | peak wired GB | peak compressor GB | min free GB | timing (short/long page) |")
    print("|---|---|---|---|---|---|---|---|")
    for path in sys.argv[1:]:
        rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        if not rows:
            continue
        name = os.path.basename(path)[4:-6]
        steps = sum(r["steps"] for r in rows)
        mem = Path(path).with_suffix(".csv")
        wired = comp = free = float("nan")
        if mem.exists():
            samples = list(csv.DictReader(mem.open()))
            if samples:
                wired = max(int(s["wired_mb"]) for s in samples) / 1024
                comp = max(int(s["compressor_mb"]) for s in samples) / 1024
                free = min(int(s["free_mb"]) for s in samples) / 1024
        timing = Path(path).with_suffix(".timing")
        tline = ""
        if timing.exists():
            parts = [line.split("median ")[-1].replace(" per call", "") for line in timing.read_text().splitlines() if "median" in line]
            tline = " / ".join(parts)
        print(
            f"| {name} | {sum(r['success'] for r in rows)}/{len(rows)} | {st.median(r['total_s'] for r in rows):.1f} | "
            f"{sum(r['total_s'] for r in rows) / max(1, steps):.2f} | {wired:.1f} | {comp:.1f} | {free:.1f} | {tline} |"
        )


if __name__ == "__main__":
    main()
