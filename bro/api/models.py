"""
Pydantic models for API requests and responses.

Defines the data structures used for communication between the API client
and the Bro agent backend.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from agent.models import Extraction, TabState, TodoItem, ActionContext, StructuredOutputContext


class RunStatus(str, Enum):
    """Status of an agent run."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_DECISION = "awaiting_decision"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class CreateRunRequest(BaseModel):
    """Request to create a new agent run."""

    user_prompt: str = Field(..., description="The task for the agent to complete")
    url: Optional[str] = Field(None, description="Optional starting URL")
    max_iterations: int = Field(100, description="Maximum number of iterations")
    model: str = Field("gpt-4o-mini", description="LLM model to use")


class CreateRunResponse(BaseModel):
    """Response after creating a new agent run."""

    run_id: str = Field(..., description="Unique identifier for this run")
    status: RunStatus = Field(..., description="Current status of the run")
    message: str = Field(..., description="Human-readable status message")


class ListRunsResponse(BaseModel):
    id: str
    status: RunStatus
    title: Optional[str]
    completed_at: Optional[str]


class AgentStateResponse(BaseModel):
    """Response containing full agent state."""

    current_tab_index: Optional[int]
    extractions: List[Extraction]
    tabs: List[TabState]
    todo_list: List[TodoItem]
    action_history: List[ActionContext]
    last_edited: str
    max_iterations: int


class SendInputRequest(BaseModel):
    """Request to send additional instructions to a running agent."""

    message: str = Field(..., description="Additional instructions for the agent")


class SendInputResponse(BaseModel):
    """Response after sending input to agent."""

    status: str = Field(..., description="Status of the input submission")
    message: str


class DecisionType(str, Enum):
    """Type of decision in response to agent completion."""

    DONE = "done"
    MODIFY = "modify"
    INTERVENE = "intervene"


class SendDecisionRequest(BaseModel):
    """Request to respond to an agent's completion prompt."""

    decision: DecisionType = Field(
        ..., description="User's decision (done/modify/intervene)"
    )
    additional_instructions: Optional[str] = Field(
        None, description="Additional instructions if decision is 'modify'"
    )


class SendDecisionResponse(BaseModel):
    """Response after sending decision to agent."""

    status: str
    message: str


class StopRunResponse(BaseModel):
    """Response after stopping a run."""

    status: RunStatus
    message: str


class CloseBrowserResponse(BaseModel):
    """Response after closing the Chrome browser."""

    status: str
    message: str


class LogType(str, Enum):
    """Type of decision in response to agent completion."""

    ACTION = "action"
    ERROR = "error"
    STATUS = "status"
    FINAL_STATUS = "final_status"
    USER_INPUT = "user_input"
    USER_DECISION = "user_decision"
    THINKING = "thinking"


class LogEvent(BaseModel):
    """A single log event for streaming."""

    timestamp: str
    iteration: int = None
    event_type: LogType
    message: Optional[str] = None
    error: Optional[str] = None
    action_context: Optional[ActionContext] = None
    thinking_context: Optional[StructuredOutputContext] = None
    decision: Optional[SendDecisionRequest] = None


class LogEventDB(LogEvent):
    id: str
    run_id: str


class RunState(BaseModel):
    id: str
    title: Optional[str]
    status: RunStatus
    user_prompt: str
    url: Optional[str]
    max_iterations: int
    model: str
    current_iteration: Optional[int]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    metadata: Optional[Dict[str, Any]]
