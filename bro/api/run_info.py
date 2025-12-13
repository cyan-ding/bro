"""
Run information for tracking individual agent sessions.

This module is separated to avoid circular imports between agent and run_manager.
"""

import asyncio
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from agent.models import ActionContext

from .models import LogType, RunStatus, LogEvent, SendDecisionRequest

if TYPE_CHECKING:
    from agent.agent import Agent


class RunInfo:
    """
    Tracks the agent instance, status, iteration progress, and provides
    queues for communication with the agent.
    """

    def __init__(
        self,
        run_id: str,
        user_id: str,
        agent: Optional["Agent"],
        max_iterations: int,
        user_prompt: str,
        url: str = None
    ):
        """
        Initialize run information.

        Args:
            run_id: Unique identifier for this run
            user_id: User identifier
            agent: The Agent instance (can be None initially)
            max_iterations: Maximum iterations for this run
            user_prompt: The user's task prompt
        """
        self.run_id = run_id
        self.user_id = user_id
        self.agent = agent
        self.max_iterations = max_iterations
        self.user_prompt = user_prompt
        self.status = RunStatus.PENDING
        self.current_iteration = 0
        self.error_message: Optional[str] = None
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.url=url

        # Task that runs the agent
        self.task: Optional[asyncio.Task] = None

        # Log events for streaming
        self.log_queue: asyncio.Queue[LogEvent] = asyncio.Queue()

    def update_iteration(self) -> None:
        """
        Update the current iteration
        """
        self.current_iteration += 1

    def set_status(self, status: RunStatus, message: Optional[str] = None) -> None:
        """
        Update the run status.

        Args:
            status: New status
            message: Optional message (e.g., error details)
        """
        self.status = status
        if message:
            self.error_message = message
        if status in [RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.ERROR]:
            self.completed_at = datetime.now()

    async def add_log_event(
        self,
        event_type: LogType,
        action_context: Optional[ActionContext] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        decision: Optional[SendDecisionRequest] = None,
    ) -> None:
        """
        Add a log event to the queue for streaming.

        Args:
            event_type: Type of event (action, thinking, result, error, status)
            action_context: Optional action context for action events
            message: Optional message text
            error: Optional error message
            decision: Optional decision request data
        """
        event = LogEvent(
            timestamp=datetime.now().isoformat(),
            iteration=self.current_iteration,
            event_type=event_type,
            action_context=action_context,
            message=message,
            error=error,
            decision=decision,
        )
        await self.log_queue.put(event)
