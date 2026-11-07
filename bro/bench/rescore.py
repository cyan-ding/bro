"""Re-judge stored results: `python -m bro.bench.rescore [--llm] results.jsonl ...` (--llm also re-runs LLM-judged tasks)."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict

from .judge import Task, judge


async def main() -> None:
    tasks: Dict[str, Task] = {}
    for path in (Path(__file__).with_name("tasks.json"), Path(__file__).with_name("tasks_webvoyager.json")):
        tasks.update({t.id: t for t in (Task(**row) for row in json.loads(path.read_text()))})
    rejudge_llm = "--llm" in sys.argv
    for file in [a for a in sys.argv[1:] if not a.startswith("--")]:
        rows = [json.loads(line) for line in Path(file).read_text().splitlines() if line.strip()]
        for row in rows:
            task = tasks.get(row["task_id"])
            if task is None or (task.check == "llm" and not rejudge_llm):
                continue
            verdict = await judge(task, row["answer"] or "")
            row["success"], row["reason"] = verdict.success, verdict.reason
        Path(file).write_text("".join(json.dumps(row) + "\n" for row in rows))


if __name__ == "__main__":
    asyncio.run(main())
