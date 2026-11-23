"""Judge Online-Mind2Web trajectories with the official WebJudge (github.com/OSU-NLP-Group/Online-Mind2Web, MIT).

The official functions are called directly, with the same prompts, score threshold and verdict parsing, instead of
through its run.py: that script's multiprocessing breaks on macOS (spawn cannot pickle its client; fork hangs).
One change: its 512-token reply cap predates reasoning backbones, which used it up and returned no verdict, so the
cap is raised to 8,192 tokens with one retry on an empty reply.

    git clone https://github.com/OSU-NLP-Group/Online-Mind2Web /tmp/om2w
    uv venv .venv-webjudge && VIRTUAL_ENV=.venv-webjudge uv pip install -r /tmp/om2w/requirements.txt
    OPENAI_API_KEY=$OPENROUTER_API_KEY OPENAI_BASE_URL=https://openrouter.ai/api/v1 PYTHONPATH=. \
      .venv-webjudge/bin/python -m bro.bench.compare.webjudge /tmp/om2w/src bro/bench/results/om2w/runs bro judged_bro.jsonl
"""

import argparse
import asyncio
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .models import Om2wResult

MODE = "WebJudge_Online_Mind2Web_eval"


def load_official(src: Path) -> Tuple[Any, Any, Any]:
    """Import OpenaiEngine, extract_predication and the WebJudge function from the official source tree."""
    sys.path.insert(0, str(src))
    from methods.webjudge_online_mind2web import WebJudge_Online_Mind2Web_eval  # type: ignore[import-not-found]
    from utils import OpenaiEngine, extract_predication  # type: ignore[import-not-found]

    generate = OpenaiEngine.generate

    def generate_with_room(self: Any, messages: List[Any], max_new_tokens: int = 512, **kwargs: Any) -> List[Optional[str]]:
        out = generate(self, messages, max_new_tokens=max(max_new_tokens, 8192), **kwargs)
        if not (out and out[0]):
            out = generate(self, messages, max_new_tokens=max(max_new_tokens, 8192), **kwargs)
        return out

    OpenaiEngine.generate = generate_with_room
    return OpenaiEngine, extract_predication, WebJudge_Online_Mind2Web_eval


def screenshots(side: Path) -> List[str]:
    trajectory = side / "trajectory"
    if not trajectory.is_dir():
        return []
    names = sorted(os.listdir(trajectory), key=lambda name: int(re.findall(r"\d+", name)[0]))
    return [str(trajectory / name) for name in names]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="the official repo's src/ directory")
    parser.add_argument("runs", help="RUNS/<task_id>/<agent>/result.json + trajectory/")
    parser.add_argument("agent", help="bro or bu")
    parser.add_argument("out", help="judged JSONL, appended to and resumed from")
    parser.add_argument("--model", default="openai/gpt-6-luna")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--threshold", type=int, default=3)
    args = parser.parse_args()
    engine_cls, extract_predication, webjudge = load_official(Path(args.src))
    model = engine_cls(model=args.model, api_key=os.environ["OPENAI_API_KEY"])
    out, runs = Path(args.out), Path(args.runs)
    done = {json.loads(line)["task_id"] for line in out.read_text().splitlines() if line.strip()} if out.exists() else set()
    lock = threading.Lock()

    def judge(task_id: str) -> Tuple[str, Optional[int]]:
        side = runs / task_id / args.agent
        result = Om2wResult(**json.loads((side / "result.json").read_text()))
        shots = screenshots(side)
        try:
            messages, _, _, record, key_points = asyncio.run(webjudge(result.task, result.action_history, shots, model, args.threshold))
            response = model.generate(messages)[0]
            label = extract_predication(response, MODE)
        except Exception as exc:
            response, label, key_points, record = f"JUDGE ERROR: {exc}", None, None, None
        row = {"task_id": task_id, "agent": args.agent, "predicted_label": label, "response": response, "key_points": key_points,
               "image_scores": [r.get("Score") if isinstance(r, dict) else None for r in (record or [])],
               "n_screenshots": len(shots), "elapsed_s": result.elapsed_s, "steps": result.steps}
        with lock, out.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        return task_id, label

    todo = [t for t in sorted(os.listdir(runs)) if t not in done and (runs / t / args.agent / "result.json").exists()]
    print(f"{len(todo)} trajectories to judge for {args.agent}", flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        for task_id, label in pool.map(judge, todo):
            print(task_id[:12], label, flush=True)


if __name__ == "__main__":
    main()
