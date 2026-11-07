"""
Run manager for tracking and managing active agent sessions.

Maintains state for all active agent runs, handles communication with agents,
and provides thread-safe access to run information.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Dict, Optional

from agent.agent import Agent
from utils.db import save_run_state

from bro.fast.llm import ChatModel
from bro.fast.local_server import ensure_local_server

from .fast_run import FastRun

from .models import RunStatus, SendDecisionRequest
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

    async def set_run(self, run_id, run_info):
        # helper to add a run
        async with self._lock:
            self._runs[run_id] = run_info

    async def get_run(self, run_id: str) -> Optional[RunInfo]:
        async with self._lock:
            return self._runs.get(run_id)

    async def create_run(
        self,
        user_prompt: str,
        url: Optional[str] = None,
        max_iterations: int = 100,
        model: str = "gemini/gemini-2.5-flash-preview-09-2025",
        mode: str = "fast",
    ) -> RunInfo:
        run_id = str(uuid.uuid4())

        # Load system prompt
        system_prompt_path = Path(__file__).parent.parent.parent / "bro.txt"
        system_prompt = system_prompt_path.read_text(encoding="utf-8")

        # generate a 3-5 word summary of the user prompt to be the title of the run

        summary_prompt = "Summarize the user's prompt concisely in 3-5 words. Reply with the summary only."
        try:
            await asyncio.to_thread(ensure_local_server, model)
            title = (await ChatModel(model, max_tokens=20).complete(summary_prompt, user_prompt)).text.strip()
        except Exception:
            title = ""
        title = title or user_prompt[:50]

        # Create run info first (without agent)
        run_info = RunInfo(
            run_id=run_id,
            agent=None,  # Will be set below
            max_iterations=max_iterations,
            user_prompt=user_prompt,
            url=url,
            title=title,
        )

        if mode == "legacy":
            agent = Agent(system_prompt=system_prompt, model=model, run_info=run_info)
        else:
            agent = FastRun(model, run_info)

        # Set the agent in run_info
        run_info.agent = agent

        await self.set_run(run_id, run_info)
        # Start the agent in background
        run_info.task = asyncio.create_task(
            self._run_agent(run_info, url, max_iterations)
        )

        # callback to verify run succeeded

        def task_done_callback(task: asyncio.Task):
            try:
                task.result()
            except asyncio.CancelledError:
                pass  # no need to log errors if its canceled
            except Exception:
                print("background task failed")
                import traceback

                traceback.print_exc()

        run_info.task.add_done_callback(task_done_callback)
        return run_info

    async def _run_agent(
        self,
        run_info: RunInfo,
        url: Optional[str],
        max_iterations: int,
    ) -> None:
        """
        Run the agent in the background.

        Args:
            run_info: Run information object
            url: Optional starting URL
            max_iterations: Maximum iterations
        """
        try:
            run_info.set_status(RunStatus.RUNNING)
            await run_info.add_log_event(
                "status", message=f"Agent run started: {run_info.user_prompt}"
            )
            await save_run_state(run_info)

            # Run the agent
            await run_info.agent.run(
                user_prompt=run_info.user_prompt,
                url=url or "",
                max_iterations=max_iterations,
                enable_input_queue=True,
            )

            run_info.set_status(RunStatus.COMPLETED)
            await run_info.add_log_event(
                "status", message="Agent run completed successfully"
            )

            await save_run_state(run_info)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            run_info.set_status(RunStatus.ERROR, str(e))
            print(e)
            await run_info.add_log_event(
                "error",
                error=str(e),
                message="Run Failed: Unable to Connect to Browser"
                if isinstance(e, TimeoutError)
                else "Agent run failed",
            )
            await save_run_state(run_info)

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
        await save_run_state(run_info)
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
        await save_run_state(run_info)
        return True

    async def get_agent_state(self, run_id: str) -> Optional[Dict]:
        run_info = await self.get_run(run_id)
        if not run_info:
            return None

        state_dict = run_info.agent.agent_state.model_dump(
            mode="json", exclude={"max_action_history", "max_extractions"}
        )

        return state_dict
