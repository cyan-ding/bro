"""Score Laya (encoder decision model) on logged states; runs in a venv that has `laya` installed.

`python -m bro.bench.replay_laya --states run.jsonl --checkpoints convaiinnovations/laya-typed-decisions --out calib.jsonl [--mlx]`
"""

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from bro.bench.replay_s1 import load_states
from bro.fast.dsl import parse_line
from bro.fast.system1 import ESCALATE_OPTIONS, SYSTEM_PROMPT, build_candidates, ideal_label


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--checkpoints", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mlx", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.6)
    args = parser.parse_args()
    runtime = __import__("laya_mlx" if args.mlx else "laya")
    states = load_states(Path(args.states))
    out = Path(args.out)
    for checkpoint in args.checkpoints:
        agent = runtime.load(checkpoint)
        name = f"laya{'-mlx' if args.mlx else ''}:{checkpoint.split('/')[-1]}"
        rows: List[Dict[str, Any]] = []
        for state in states:
            candidates = build_candidates(state.obs, state.task)
            text = (
                f"Task: {state.task}\nNotes: {'; '.join(state.notes) or '(none)'}\nRecent actions:\n{chr(10).join(state.history[-4:]) or '(none yet)'}\n"
                f"Page: {state.obs.title[:80]} | {state.obs.url[:100]}\nVisible text: {state.obs.text[:500]}"
            )
            question = {
                "next": {
                    "type": "choice",
                    "instructions": SYSTEM_PROMPT.split("Reply with")[0].strip() + " Which option is the best next action?",
                    "criteria": {c.label: c.line[:160] for c in candidates},
                }
            }
            started = time.perf_counter()
            try:
                answer = agent.predict(text, question)["answers"]["next"]
                error = ""
            except Exception as exc:
                answer, error = {}, str(exc)[:160]
            latency_ms = int((time.perf_counter() - started) * 1000)
            probs = {k: float(v) for k, v in (answer.get("probabilities") or {}).items()}
            label = max(probs, key=probs.get) if probs else None
            by_label = {c.label: c for c in candidates}
            choice = by_label.get(label) if label else None
            confidence = probs.get(label, 0.0) if label else 0.0
            escalate = choice is None or choice.action.name in ESCALATE_OPTIONS or confidence < args.threshold
            action = parse_line(state.s2_action)
            ideal = ideal_label(action, candidates) if action else ""
            rows.append(
                {
                    "s1": name,
                    "task_id": state.task_id,
                    "step": state.step,
                    "s2_action": state.s2_action,
                    "label": label,
                    "action": str(choice.action) if choice else None,
                    "confidence": round(confidence, 4),
                    "latency_ms": latency_ms,
                    "prompt_tokens": 0,
                    "escalate": escalate,
                    "ideal": ideal,
                    "agrees": bool(choice and choice.label == ideal),
                    "ideal_is_action": bool(action and action.name in ("click", "scroll", "back")) and ideal not in {c.label for c in candidates if c.action.name in ESCALATE_OPTIONS},
                    "reason": error or ("confident" if not escalate else "escalate"),
                }
            )
        with out.open("a") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
