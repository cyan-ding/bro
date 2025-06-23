from typing import List, Literal

from pydantic import BaseModel, Field


class InformationRequirements(BaseModel):
    internal: List[str]
    external: List[str]


class CeoSubgoal(BaseModel):
    id: str
    description: str
    type: Literal["SEQUENTIAL", "PARALLEL", "CONTEXT_DEPENDENT"]
    priority: int = Field(ge=1, le=5)
    dependencies: List[str]
    information_requirements: InformationRequirements
    success_criteria: str


class CeoResponse(BaseModel):
    subgoals: List[CeoSubgoal]
    execution_order: List[str]
    parallel_groups: List[List[str]]
