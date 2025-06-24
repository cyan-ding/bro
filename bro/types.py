from typing import List, Literal, Optional

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


class Target(BaseModel):
    selector: str
    text: Optional[str] = None
    attribute: Optional[str] = None


class Parameters(BaseModel):
    text: Optional[str] = None
    direction: Optional[Literal["up", "down", "left", "right"]] = None
    url: Optional[str] = None


class FallbackAction(BaseModel):
    type: Literal["DELETE", "CLICK", "WRITE", "SCROLL", "NAVIGATE"]
    description: str


class ManagerSubgoal(BaseModel):
    id: str
    type: Literal["DELETE", "CLICK", "WRITE", "SCROLL", "NAVIGATE"]
    description: str
    target: Target
    parameters: Parameters
    prerequisites: List[str]
    fallback_actions: List[FallbackAction]
    parallizability: int
    success_criteria: str


class ManagerResponse(BaseModel):
    atomic_tasks: List[ManagerSubgoal]
    execution_order: List[str]
    requires_user_confirmation: bool
