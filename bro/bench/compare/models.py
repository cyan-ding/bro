"""Records shared by both environments (only pydantic is imported here)."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class RecordedRun(BaseModel):
    """One agent's run of one task, written as result.json next to its frames."""

    agent: str
    model: str
    task_id: str
    answer: Optional[str] = None
    error: Optional[str] = None
    steps: Optional[int] = None
    elapsed_s: float
    cost_usd: Optional[float] = None
    success: Optional[bool] = None
    judge: Optional[str] = None


class BrowserUseRecord(BaseModel):
    """One line of the browser-use benchmark results file."""

    task_id: str
    agent: str
    model: str
    answer: Optional[str] = None
    steps: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None
    usage: Dict[str, int] = {}
    total_s: float


class ScreencastIndex(BaseModel):
    """Frame files (relative to the frames directory) with their seconds since recording started."""

    frames: List[Tuple[float, str]]
    end: float


class TaskSpec(BaseModel):
    id: str
    task: str
    url: str


def load_task_specs(path: Path) -> Dict[str, TaskSpec]:
    return {t["id"]: TaskSpec(**t) for t in json.loads(path.read_text())}
