"""Score candidate System 1 models offline on logged page states: one model loaded at a time.

`python -m bro.bench.replay_s1 --states run.jsonl --s1 local/... jev --out calib.jsonl`
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel

from bro.fast.dsl import parse_line
from bro.fast.local_server import stop_server
from bro.fast.observe import Observation
from bro.fast.system1 import ideal_label, make_system1
from bro.utils.env_loader import load_env_files


class State(BaseModel):
    task_id: str
    step: int
    obs: Observation
    history: List[str]
    notes: List[str]
    task: str
    s2_action: str


def load_states(path: Path) -> List[State]:
    states: List[State] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for step in row["result"]["steps"]:
            if step.get("state") and step["step"] > 1:
                states.append(
                    State(
                        task_id=row["task_id"],
                        step=step["step"],
                        obs=Observation(**step["state"]["obs"]),
                        history=step["state"]["history"],
                        notes=step["state"]["notes"],
                        task=step["state"]["task"],
                        s2_action=step["actions"][0] if step["actions"] else "none",
                    )
                )
    return states


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--s1", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    load_env_files()
    states = load_states(Path(args.states))
    out = Path(args.out)
    for spec in args.s1:
        try:
            scorer = make_system1(spec)
        except (MemoryError, TimeoutError) as exc:
            with out.open("a") as handle:
                handle.write(json.dumps({"s1": spec, "skipped": str(exc)}) + "\n")
            continue
        rows: List[Dict[str, Any]] = []
        for state in states:
            decision = await scorer.decide(state.task, state.notes, state.history, state.obs)
            action = parse_line(state.s2_action)
            ideal = ideal_label(action, decision.candidates) if action and decision.candidates else ""
            rows.append(
                {
                    "s1": spec,
                    "task_id": state.task_id,
                    "step": state.step,
                    "s2_action": state.s2_action,
                    "label": decision.choice.label if decision.choice else None,
                    "action": str(decision.choice.action) if decision.choice else None,
                    "confidence": round(decision.confidence, 4),
                    "latency_ms": decision.latency_ms,
                    "prompt_tokens": decision.prompt_tokens,
                    "escalate": decision.escalate,
                    "ideal": ideal,
                    "agrees": bool(decision.choice and decision.choice.label == ideal),
                    "ideal_is_action": bool(action and action.name in ("click", "scroll", "back")) and ideal not in {c.label for c in decision.candidates if c.action.name in ("type", "done", "none")},
                    "reason": decision.reason,
                }
            )
        with out.open("a") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        if spec.startswith("local/"):
            stop_server(spec.partition("#")[0])


if __name__ == "__main__":
    asyncio.run(main())
