"""
Mock run manager for testing the frontend without running actual agents.

Simulates realistic agent behavior including log streaming, state updates,
and status transitions without executing real web automation.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional
from .models import RunStatus, LogEvent
from .run_info import RunInfo


class MockAgent:
    """Mock agent that simulates agent state without real execution."""

    def __init__(self):
        """Initialize mock agent with simulated state."""
        self.agent_state = MockAgentState()
        self.input_manager = MockInputManager()


class MockAgentState:
    """Mock agent state with simulated data."""

    def to_dict(self) -> Dict:
        """
        Convert mock agent state to dictionary.

        Returns:
            Dictionary representation of mock agent state
        """
        return {
            "user_id": "test_user",
            "session_id": "test_session",
            "current_tab_index": 0,
            "extractions": [
                {
                    "type": "data",
                    "content": "Mock extraction: Found product price $29.99",
                    "timestamp": datetime.now().isoformat()
                }
            ],
            "tabs": [
                {
                    "id": "tab_1",
                    "url": "https://example.com",
                    "title": "Example Domain - Mock Page",
                    "is_active": True
                }
            ],
            "todo_list": [
                {"task": "Navigate to website", "status": "completed"},
                {"task": "Extract product information", "status": "in_progress"},
                {"task": "Verify checkout process", "status": "pending"}
            ],
            "action_history": [
                {
                    "iteration": 1,
                    "action": "navigate",
                    "details": "Navigated to https://example.com",
                    "timestamp": datetime.now().isoformat()
                },
                {
                    "iteration": 2,
                    "action": "click",
                    "details": "Clicked on 'Products' link",
                    "timestamp": datetime.now().isoformat()
                }
            ],
            "last_edited": datetime.now().isoformat()
        }


class MockInputManager:
    """Mock input manager with queues for communication."""

    def __init__(self):
        """Initialize mock input manager with message and decision queues."""
        self.message_queue: asyncio.Queue[str] = asyncio.Queue()
        self.decision_queue: asyncio.Queue[str] = asyncio.Queue()


class MockRunManager:
    """
    Mock run manager that simulates agent behavior.

    Provides the same interface as RunManager but generates fake data
    instead of running actual agents.
    """

    def __init__(self):
        """Initialize the mock run manager."""
        self._runs: Dict[str, RunInfo] = {}
        self._lock = asyncio.Lock()

    async def create_run(
        self,
        user_prompt: str,
        url: Optional[str] = None,
        max_iterations: int = 100,
        take_screenshot: bool = True,
        model: str = "gpt-4o-mini",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        enable_logging: bool = False,
    ) -> RunInfo:
        """
        Create a mock agent run.

        Args:
            user_prompt: The task for the agent to complete
            url: Optional starting URL
            max_iterations: Maximum number of iterations
            take_screenshot: Whether to take screenshots
            model: LLM model to use
            user_id: User identifier
            session_id: Session identifier
            enable_logging: Whether to enable log streaming

        Returns:
            RunInfo object for the created run
        """
        run_id = str(uuid.uuid4())
        if not session_id:
            session_id = str(uuid.uuid4())[:8]
        if not user_id:
            user_id = "test_user"

        # Create mock agent
        agent = MockAgent()

        # Create run info
        run_info = RunInfo(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent=agent,
            max_iterations=max_iterations,
            user_prompt=user_prompt,
        )

        async with self._lock:
            self._runs[run_id] = run_info

        # Start mock agent execution
        run_info.task = asyncio.create_task(
            self._simulate_agent_run(run_info, url)
        )

        return run_info

    async def _simulate_agent_run(
        self,
        run_info: RunInfo,
        url: Optional[str],
    ) -> None:
        """
        Simulate an agent run with realistic log events.

        Args:
            run_info: Run information object
            url: Optional starting URL
        """
        try:
            run_info.set_status(RunStatus.RUNNING)
            await run_info.add_log_event(
                "status",
                {"message": "Agent run started", "user_prompt": run_info.user_prompt}
            )

            # Simulate multiple iterations
            for i in range(1, 6):
                run_info.update_iteration(i, f"mock_action_{i}")

                # Simulate navigation
                if i == 1:
                    await asyncio.sleep(0.5)
                    await run_info.add_log_event(
                        "action",
                        {
                            "action": "navigate",
                            "url": url or "https://example.com",
                            "message": f"Navigating to {url or 'https://example.com'}"
                        }
                    )

                # Simulate thinking
                await asyncio.sleep(0.8)
                await run_info.add_log_event(
                    "thinking",
                    {
                        "message": f"Iteration {i}: Analyzing page content and determining next action..."
                    }
                )

                # Simulate various actions
                actions = [
                    {"action": "click", "target": "button.submit", "message": "Clicking submit button"},
                    {"action": "type", "target": "input#search", "text": "test query", "message": "Typing into search field"},
                    {"action": "scroll", "direction": "down", "message": "Scrolling down page"},
                    {"action": "extract", "data": "Product: Widget, Price: $29.99", "message": "Extracting product information"},
                ]

                action = actions[i % len(actions)]
                await asyncio.sleep(0.6)
                await run_info.add_log_event("action", action)

                # Simulate result
                await asyncio.sleep(0.4)
                await run_info.add_log_event(
                    "result",
                    {
                        "success": True,
                        "message": f"Action completed successfully at iteration {i}"
                    }
                )

            # Simulate awaiting decision
            run_info.set_status(RunStatus.AWAITING_DECISION)
            await run_info.add_log_event(
                "status",
                {"message": "Task appears complete. Awaiting user decision."}
            )

            # Wait for decision or timeout
            try:
                decision = await asyncio.wait_for(
                    run_info.agent.input_manager.decision_queue.get(),
                    timeout=300.0  # 5 minutes
                )

                if decision.lower() in ['d', 'done']:
                    run_info.set_status(RunStatus.COMPLETED)
                    await run_info.add_log_event(
                        "status",
                        {"message": "Agent run completed successfully"}
                    )
                elif decision.lower() in ['m', 'modify']:
                    # Get additional instructions
                    instructions = await asyncio.wait_for(
                        run_info.agent.input_manager.decision_queue.get(),
                        timeout=30.0
                    )
                    run_info.set_status(RunStatus.RUNNING)
                    await run_info.add_log_event(
                        "status",
                        {"message": f"Resuming with modifications: {instructions}"}
                    )
                    # Simulate one more iteration
                    await asyncio.sleep(2)
                    run_info.set_status(RunStatus.COMPLETED)
                    await run_info.add_log_event(
                        "status",
                        {"message": "Modifications complete"}
                    )

            except asyncio.TimeoutError:
                run_info.set_status(RunStatus.COMPLETED)
                await run_info.add_log_event(
                    "status",
                    {"message": "Auto-completed after timeout"}
                )

        except asyncio.CancelledError:
            run_info.set_status(RunStatus.STOPPED)
            await run_info.add_log_event("status", {"message": "Agent run stopped by user"})
            raise
        except Exception as e:
            run_info.set_status(RunStatus.ERROR, str(e))
            await run_info.add_log_event(
                "error",
                {"error": str(e), "message": "Agent run failed"}
            )

    async def get_run(self, run_id: str) -> Optional[RunInfo]:
        """
        Get run information by ID.

        Args:
            run_id: Run identifier

        Returns:
            RunInfo object or None if not found
        """
        async with self._lock:
            return self._runs.get(run_id)

    async def stop_run(self, run_id: str) -> bool:
        """
        Stop a mock agent run.

        Args:
            run_id: Run identifier

        Returns:
            True if stopped successfully, False otherwise
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        if run_info.status not in [RunStatus.RUNNING, RunStatus.AWAITING_DECISION]:
            return False

        if run_info.task and not run_info.task.done():
            run_info.task.cancel()

        run_info.set_status(RunStatus.STOPPED)
        await run_info.add_log_event("status", {"message": "Agent run stopped by user"})

        return True

    async def send_input(self, run_id: str, message: str) -> bool:
        """
        Send mock input to agent.

        Args:
            run_id: Run identifier
            message: Message to send

        Returns:
            True if sent successfully, False otherwise
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        await run_info.agent.input_manager.message_queue.put(message)
        await run_info.add_log_event(
            "user_input",
            {"message": message}
        )

        return True

    async def send_decision(
        self,
        run_id: str,
        decision: str,
        additional_instructions: Optional[str] = None
    ) -> bool:
        """
        Send mock decision to agent.

        Args:
            run_id: Run identifier
            decision: Decision type (done/modify/intervene)
            additional_instructions: Optional additional instructions

        Returns:
            True if sent successfully, False otherwise
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return False

        await run_info.agent.input_manager.decision_queue.put(decision)

        if decision.lower() in ['m', 'modify'] and additional_instructions:
            await run_info.agent.input_manager.decision_queue.put(additional_instructions)

        await run_info.add_log_event(
            "user_decision",
            {"decision": decision, "additional_instructions": additional_instructions}
        )

        if decision.lower() in ['d', 'done']:
            run_info.set_status(RunStatus.COMPLETED)
        else:
            run_info.set_status(RunStatus.RUNNING)

        return True

    async def get_agent_state(self, run_id: str) -> Optional[Dict]:
        """
        Get mock agent state.

        Args:
            run_id: Run identifier

        Returns:
            Mock agent state dictionary or None if not found
        """
        run_info = await self.get_run(run_id)
        if not run_info:
            return None

        state_dict = run_info.agent.agent_state.to_dict()
        state_dict["run_id"] = run_id

        return state_dict
