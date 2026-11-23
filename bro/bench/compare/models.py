"""Records shared by both environments (only pydantic is imported here)."""

import json
import shutil
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


class Om2wResult(BaseModel):
    """Online-Mind2Web trajectory record, the v1 result.json that WebJudge reads (plus our timing fields)."""

    task_id: str
    task: str
    action_history: List[str]
    final_result_response: str
    agent: str
    model: str
    steps: Optional[int] = None
    elapsed_s: float
    error: Optional[str] = None


def load_om2w_tasks(path: Path) -> Dict[str, TaskSpec]:
    """Online_Mind2Web.json rows (task_id, confirmed_task, website) as TaskSpecs."""
    return {t["task_id"]: TaskSpec(id=t["task_id"], task=t["confirmed_task"], url=t["website"]) for t in json.loads(path.read_text())}


def write_trajectory(frames_dir: Path, out_dir: Path, n_actions: int, max_images: int = 25) -> int:
    """Copy one screencast frame per action, evenly spaced in time and ending on the last frame, to out_dir/trajectory/N.jpg
    (the layout WebJudge reads), then delete the full screencast. Returns the number of screenshots written."""
    index = ScreencastIndex(**json.loads((frames_dir / "index.json").read_text()))
    trajectory = out_dir / "trajectory"
    trajectory.mkdir(parents=True, exist_ok=True)
    k = max(1, min(n_actions, max_images))
    times = [f[0] for f in index.frames]
    written = 0
    for i in range(k):
        t = index.end * (i + 1) / k
        j = max(0, max((n for n, ft in enumerate(times) if ft <= t), default=0))
        if index.frames:
            shutil.copy(frames_dir / index.frames[j][1], trajectory / f"{i}.jpg")
            written += 1
    shutil.rmtree(frames_dir, ignore_errors=True)
    return written
