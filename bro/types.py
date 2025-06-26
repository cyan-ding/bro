from typing import List, Literal, Optional, Dict

from pydantic import BaseModel


class InformationRequirements(BaseModel):
    internal: List[str]
    external: List[str]


class CeoSubgoal(BaseModel):
    id: str
    description: str
    type: Literal["SEQUENTIAL", "PARALLEL", "CONTEXT_DEPENDENT"]
    priority: int
    dependencies: List[str]
    information_requirements: InformationRequirements
    success_criteria: str


class CeoResponse(BaseModel):
    subgoals: List[CeoSubgoal]
    execution_order: List[str]
    parallel_groups: List[List[str]]


class CerebrasCeo(BaseModel):
    subgoals: List[CeoSubgoal]
    execution_order: List[str]
    parallel_groups: List[List[str]]
    id: str
    choices: List
    created: int
    model: Optional[str]
    object: str
    system_fingerprint: Optional[str]
    usage: Optional[Dict[str, int]]


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
