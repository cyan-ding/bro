"""Records shared by the demo runner and the compositor."""

from typing import List, Optional

from pydantic import BaseModel


class DemoTask(BaseModel):
    id: str
    label: str
    url: str
    task: str


class TaskResult(BaseModel):
    id: str
    label: str
    start: float
    end: float = 0
    answer: Optional[str] = None
    steps: Optional[int] = None
    error: Optional[str] = None


class Sample(BaseModel):
    """One reading per second: which app is in front, whether it is Bro's own Chrome, and free system memory."""

    t: float
    front: str
    agent_front: bool
    free_pct: int


class Timeline(BaseModel):
    start_epoch: float
    end: Optional[float] = None
    tasks: List[TaskResult] = []
    samples: List[Sample] = []
