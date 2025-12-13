"""
Run manager for tracking and managing active agent sessions.

Maintains state for all active agent runs, handles communication with agents,
and provides thread-safe access to run information.
"""

import asyncio
import uuid
from typing import Dict, Optional
from pathlib import Path

from agent.agent import Agent
from utils.db import save_run_state
from .models import RunState, RunStatus, SendDecisionRequest
from .run_info import RunInfo


class RunManager:
    """
    Manages all active agent runs.

    Provides thread-safe operations for creating, tracking, and controlling
    agent runs. Maintains a registry of all active runs and handles cleanup.
    """

    def __init__(self):
        """Initialize the run manager."""
        self._runs: Dict[str, RunInfo] = {}
        self._lock = asyncio.Lock()

    async def create_run(
        self,
        user_prompt: str,
        url: Optional[str] = None,
        max_iterations: int = 100,
        take_screenshot: bool = True,
        model: str = "gemini/gemini-2.5-flash-preview-09-2025",
        user_id: Optional[str] = None,
        enable_logging: bool = True,
    ) -> RunInfo:
        run_id = str(uuid.uuid4())
        if not user_id:
            user_id = "00000000-0000-0000-0000-000000000000"  # Null UUID for anonymous users

        # Load system prompt
        system_prompt_path = Path(__file__).parent.parent.parent / "bro.txt"
        system_prompt = system_prompt_path.read_text(encoding="utf-8")

        # Create run info first (without agent)
        run_info = RunInfo(
            run_id=run_id,
            user_id=user_id,
            agent=None,  # Will be set below
            max_iterations=max_iterations,
            user_prompt=user_prompt,
            url=url
        )

        # Create agent instance with run_info if logging is enabled
        agent = Agent(
            system_prompt=system_prompt,
            user_id=user_id,
            model=model,
            run_info=run_info if enable_logging else None,
        )

        # Set the agent in run_info
        run_info.agent = agent

        async with self._lock:
            self._runs[run_id] = run_info

        # Start the agent in background
        run_info.task = asyncio.create_task(
            self._run_agent(run_info, url, max_iterations, take_screenshot)
        )

        # temporary callback 

        def task_done_callback(task: asyncio.Task):
            try:
                task.result()
            except Exception as e:
                print("background task failed")
                import traceback
                traceback.print_exc()
        run_info.task.add_done_callback(task_done_callback)
        print("Agent running with model ", model)
        return run_info

    async def _run_agent(
        self,
        run_info: RunInfo,
        url: Optional[str],
        max_iterations: int,
        take_screenshot: bool,
    ) -> None:
        """
        Run the agent in the background.

        Args:
            run_info: Run information object
            url: Optional starting URL
            max_iterations: Maximum iterations
            take_screenshot: Whether to take screenshots
        """
        try:
            run_info.set_status(RunStatus.RUNNING)
            await run_info.add_log_event(
                "status", message=f"Agent run started: {run_info.user_prompt}"
            )
            await save_run_state(
                RunState(
                    id=run_info.run_id,
                    user_id=run_info.user_id,
                    status=run_info.status,
                    user_prompt=run_info.user_prompt,
                    url=url,
                    max_iterations=max_iterations,
                    model=run_info.agent.model,
                    current_iteration=run_info.current_iteration,
                    error_message=run_info.error_message,
                    created_at=run_info.created_at,
                    completed_at=None,
                    metadata={}
                )
            )
            # Run the agent
            await run_info.agent.run(
                user_prompt=run_info.user_prompt,
                url=url or "",
                max_iterations=max_iterations,
                take_screenshot=take_screenshot,
                enable_input_queue=True,
            )

            run_info.set_status(RunStatus.COMPLETED)
            await run_info.add_log_event(
                "status", message="Agent run completed successfully"
            )

            await save_run_state(
                RunState(
                    id=run_info.run_id,
                    user_id=run_info.user_id,
                    status=run_info.status,
                    user_prompt=run_info.user_prompt,
                    url=url,
                    max_iterations=max_iterations,
                    model=run_info.agent.model,
                    current_iteration=run_info.current_iteration,
                    error_message=run_info.error_message,
                    created_at=run_info.created_at,
                    completed_at=run_info.completed_at,
                    metadata=run_info.agent.agent_state.model_dump()
                )
            )

        except Exception as e:
            run_info.set_status(RunStatus.ERROR, str(e))
            await run_info.add_log_event(
                "error", error=str(e), message="Agent run failed"
            )
            await save_run_state(
                RunState(
                    id=run_info.run_id,
                    user_id=run_info.user_id,
                    status=run_info.status,
                    user_prompt=run_info.user_prompt,
                    url=url,
                    max_iterations=max_iterations,
                    model=run_info.agent.model,
                    current_iteration=run_info.current_iteration,
                    error_message=run_info.error_message,
                    created_at=run_info.created_at,
                    completed_at=run_info.completed_at,
                    metadata=run_info.agent.agent_state.model_dump()
                )
            )

    async def get_run(self, run_id: str) -> Optional[RunInfo]:
        async with self._lock:
            return self._runs.get(run_id)

    async def stop_run(self, run_id: str) -> bool:
        """
        Stop a running agent.

        Args:
            run_id: Run identifier

        Returns:
            True if stopped successfully, False if not found or already stopped
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        if run_info.status not in [RunStatus.RUNNING, RunStatus.AWAITING_DECISION]:
            return False

        if run_info.task and not run_info.task.done():
            run_info.task.cancel()

        run_info.set_status(RunStatus.STOPPED)
        await run_info.add_log_event("status", message="Agent run stopped by user")

        return True

    async def send_input(self, run_id: str, message: str) -> bool:
        """
        Send additional instructions to a running agent.

        Args:
            run_id: Run identifier
            message: Message to send to the agent

        Returns:
            True if sent successfully, False if run not found or not running
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        if not run_info.agent.input_manager:
            return False

        await run_info.agent.input_manager.message_queue.put(message)
        await run_info.add_log_event("user_input", message=message)

        return True

    async def send_decision(
        self, run_id: str, decision: str, additional_instructions: Optional[str] = None
    ) -> bool:
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        if not run_info.agent.input_manager:
            return False

        # Send the decision
        await run_info.agent.input_manager.decision_queue.put(decision)

        # If modify with instructions, also send the instructions
        if decision.lower() in ["m", "modify"] and additional_instructions:
            await run_info.agent.input_manager.decision_queue.put(
                additional_instructions
            )

        await run_info.add_log_event(
            "user_decision",
            decision=SendDecisionRequest(
                decision=decision, additional_instructions=additional_instructions
            ),
        )

        # Update status if done
        if decision.lower() in ["d", "done"]:
            run_info.set_status(RunStatus.COMPLETED)
        else:
            run_info.set_status(RunStatus.RUNNING)
        await save_run_state(
                RunState(
                    id=run_info.run_id,
                    user_id=run_info.user_id,
                    status=run_info.status,
                    user_prompt=run_info.user_prompt,
                    url=run_info.url,
                    max_iterations=run_info.max_iterations,
                    model=run_info.agent.model,
                    current_iteration=run_info.current_iteration,
                    error_message=run_info.error_message,
                    created_at=run_info.created_at,
                    completed_at=run_info.completed_at,
                    metadata=run_info.agent.agent_state.model_dump()
                )
            )
        return True

    async def get_agent_state(self, run_id: str) -> Optional[Dict]:
        run_info = await self.get_run(run_id)
        if not run_info:
            return None

        state_dict = run_info.agent.agent_state.model_dump(
            mode="json", exclude={"max_action_history", "max_extractions"}
        )

        return state_dict
