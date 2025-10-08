"""
Pydantic models for API requests and responses.

Defines the data structures used for communication between the API client
and the Bro agent backend.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


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
    take_screenshot: bool = Field(True, description="Whether to take screenshots")
    model: str = Field("gpt-4o-mini", description="LLM model to use")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier (auto-generated if not provided)")
    enable_logging: bool = Field(False, description="Whether to enable log streaming")


class CreateRunResponse(BaseModel):
    """Response after creating a new agent run."""
    run_id: str = Field(..., description="Unique identifier for this run")
    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    status: RunStatus = Field(..., description="Current status of the run")
    message: str = Field(..., description="Human-readable status message")


class RunStatusResponse(BaseModel):
    """Response for run status queries."""
    run_id: str
    session_id: str
    user_id: str
    status: RunStatus
    current_iteration: int = Field(..., description="Current iteration number")
    max_iterations: int
    last_action: Optional[str] = Field(None, description="Last action taken by agent")
    message: Optional[str] = Field(None, description="Additional status information")


class AgentStateResponse(BaseModel):
    """Response containing full agent state."""
    run_id: str
    user_id: str
    session_id: str
    current_tab_index: Optional[int]
    extractions: List[Dict[str, Any]]
    tabs: List[Dict[str, Any]]
    todo_list: List[Dict[str, Any]]
    action_history: List[Dict[str, Any]]
    last_edited: str


class SendInputRequest(BaseModel):
    """Request to send additional instructions to a running agent."""
    message: str = Field(..., description="Additional instructions for the agent")


class SendInputResponse(BaseModel):
    """Response after sending input to agent."""
    run_id: str
    status: str = Field(..., description="Status of the input submission")
    message: str


class DecisionType(str, Enum):
    """Type of decision in response to agent completion."""
    DONE = "done"
    MODIFY = "modify"
    INTERVENE = "intervene"


class SendDecisionRequest(BaseModel):
    """Request to respond to an agent's completion prompt."""
    decision: DecisionType = Field(..., description="User's decision (done/modify/intervene)")
    additional_instructions: Optional[str] = Field(None, description="Additional instructions if decision is 'modify'")


class SendDecisionResponse(BaseModel):
    """Response after sending decision to agent."""
    run_id: str
    status: str
    message: str

class StopRunResponse(BaseModel):
    """Response after stopping a run."""
    run_id: str
    status: RunStatus
    message: str


class CloseBrowserResponse(BaseModel):
    """Response after closing the Chrome browser."""
    status: str
    message: str


class LogEvent(BaseModel):
    """A single log event for streaming."""
    timestamp: str
    run_id: str
    iteration: Optional[int] = None
    event_type: str = Field(..., description="Type of event (action, thinking, result, error, status)")
    data: Dict[str, Any] = Field(..., description="Event data")
