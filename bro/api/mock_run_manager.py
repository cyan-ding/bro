"""
Mock run manager for testing the frontend without running actual agents.

Simulates realistic agent behavior including log streaming, state updates,
and status transitions without executing real web automation.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional

from agent.agent_state import AgentState
from agent.models import ActionContext, StructuredOutputContext

from .models import DecisionType, LogType, RunStatus, SendDecisionRequest
from .run_info import RunInfo


class MockAgent:
    """Mock agent that simulates agent state without real execution."""

    def __init__(self):
        """
        Initialize mock agent with simulated state.
        """
        self.agent_state = AgentState()
        self.input_manager = MockInputManager()

        # Populate with mock data
        self._initialize_mock_state()

    def _initialize_mock_state(self) -> None:
        """Initialize the agent state with realistic mock data."""
        # Add mock extraction
        self.agent_state.add_extraction(
            content="Mock extraction: Found product price $29.99",
            source_url="https://example.com",
            source_title="Example Domain - Mock Page",
        )

        # Add mock tab
        self.agent_state.add_tab_state(
            url="https://example.com",
            title="Example Domain - Mock Page",
            is_active=True,
        )

        # Add mock todo items
        self.agent_state.update_todo_list(
            [
                {"task": "Navigate to website", "completed": True},
                {"task": "Extract product information", "completed": False},
                {"task": "Verify checkout process", "completed": False},
            ]
        )

        # Add mock action history
        self.agent_state.action_history.append(
            ActionContext(
                iteration=1,
                action_name="navigate",
                arguments={"url": "https://example.com"},
                result="Successfully navigated to https://example.com",
                timestamp=datetime.now().isoformat(),
                description="Navigating to initial URL",
                structured_output=StructuredOutputContext(
                    thinking="I need to navigate to the target website first",
                    evaluation_previous_actions="No previous actions yet",
                    memory="Starting fresh navigation",
                    next_goal="Navigate to https://example.com",
                ),
            )
        )
        self.agent_state.action_history.append(
            ActionContext(
                iteration=2,
                action_name="click",
                arguments={"element_id": "123", "selector": "button.products"},
                result="Clicked on 'Products' link",
                timestamp=datetime.now().isoformat(),
                description="Clicking products button",
                structured_output=StructuredOutputContext(
                    thinking="The products button should lead to the product catalog",
                    evaluation_previous_actions="Successfully navigated to homepage",
                    memory="On homepage, found products button",
                    next_goal="Access product catalog",
                ),
            )
        )


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
            enable_logging: Whether to enable log streaming

        Returns:
            RunInfo object for the created run
        """
        run_id = str(uuid.uuid4())

        # Create mock agent
        agent = MockAgent()

        # Create run info
        run_info = RunInfo(
            run_id=run_id,
            agent=agent,
            max_iterations=max_iterations,
            user_prompt=user_prompt,
        )

        async with self._lock:
            self._runs[run_id] = run_info

        # Start mock agent execution
        run_info.task = asyncio.create_task(self._simulate_agent_run(run_info, url))

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
                LogType.STATUS, message=f"Agent run started: {run_info.user_prompt}"
            )

            # Simulate multiple iterations
            for i in range(1, 6):
                run_info.update_iteration()

                # Simulate navigation
                if i == 1:
                    await asyncio.sleep(0.5)
                    action_ctx = ActionContext(
                        iteration=i,
                        action_name="navigate",
                        arguments={"url": url or "https://example.com"},
                        result=f"Navigating to {url or 'https://example.com'}",
                        description=f"Navigating to {url or 'https://example.com'}",
                        structured_output=StructuredOutputContext(
                            thinking="The agent should visit the starting URL.",
                            evaluation_previous_actions="",
                            memory="",
                            next_goal="Arrive at the page and analyze content.",
                        ),
                    )
                    await run_info.add_log_event(
                        LogType.ACTION, action_context=action_ctx
                    )

                # Simulate thinking action
                await asyncio.sleep(0.8)
                thinking_ctx = ActionContext(
                    iteration=i,
                    action_name="thinking",
                    arguments={},
                    result="",
                    description="Agent is thinking",
                    structured_output=StructuredOutputContext(
                        thinking=f"Iteration {i}: Analyzing page content and determining next action...",
                        evaluation_previous_actions=f"Completed {i - 1} actions so far",
                        memory="Processing current page state",
                        next_goal="Determine the best action to take next",
                    ),
                )
                await run_info.add_log_event(
                    LogType.ACTION, action_context=thinking_ctx
                )

                # Simulate various actions with proper ActionContext structure
                actions = [
                    ActionContext(
                        iteration=i,
                        action_name="click",
                        arguments={
                            "element_id": "submit_btn",
                            "selector": "button.submit",
                        },
                        result="Successfully clicked submit button",
                        timestamp=datetime.now().isoformat(),
                        description="Clicking submit button",
                        structured_output=StructuredOutputContext(
                            thinking="Need to submit the form to proceed",
                            evaluation_previous_actions=f"Completed {i - 1} actions successfully",
                            memory="Form filled, ready to submit",
                            next_goal="Submit form and wait for response",
                        ),
                    ),
                    ActionContext(
                        iteration=i,
                        action_name="input_text",
                        arguments={
                            "element_id": "search_input",
                            "selector": "input#search",
                            "text": "test query",
                        },
                        result="Successfully typed into search field",
                        timestamp=datetime.now().isoformat(),
                        description="Typing into search field",
                        structured_output=StructuredOutputContext(
                            thinking="I should search for the relevant information",
                            evaluation_previous_actions=f"Navigation complete at iteration {i - 1}",
                            memory="Located search field on page",
                            next_goal="Execute search query",
                        ),
                    ),
                    ActionContext(
                        iteration=i,
                        action_name="scroll",
                        arguments={"direction": "down", "amount": 500},
                        result="Scrolled down 500 pixels",
                        timestamp=datetime.now().isoformat(),
                        description="Scrolling down page",
                        structured_output=StructuredOutputContext(
                            thinking="Need to scroll to see more content",
                            evaluation_previous_actions="Page loaded but content below fold",
                            memory="Page has additional content below",
                            next_goal="View content further down the page",
                        ),
                    ),
                    ActionContext(
                        iteration=i,
                        action_name="extract",
                        arguments={"selector": "div.product-info", "field": "text"},
                        result="Extracted: Product: Widget, Price: $29.99",
                        timestamp=datetime.now().isoformat(),
                        description="Extracting product information",
                        structured_output=StructuredOutputContext(
                            thinking="Found the product information I need to extract",
                            evaluation_previous_actions="Successfully navigated to product page",
                            memory="Located product details section",
                            next_goal="Extract and store product data",
                        ),
                    ),
                ]

                action_ctx = actions[i % len(actions)]
                await asyncio.sleep(0.6)
                await run_info.add_log_event(LogType.ACTION, action_context=action_ctx)

            # Decision loop - keeps awaiting decisions until user says "done"
            while True:
                # Simulate awaiting decision
                run_info.set_status(RunStatus.AWAITING_DECISION)
                await run_info.add_log_event(
                    LogType.STATUS,
                    message="Task appears complete. Awaiting user decision.",
                )

                # Wait for decision or timeout
                try:
                    decision = await asyncio.wait_for(
                        run_info.agent.input_manager.decision_queue.get(),
                        timeout=300.0,  # 5 minutes
                    )

                    if decision.lower() in ["d", "done"]:
                        run_info.set_status(RunStatus.COMPLETED)
                        await run_info.add_log_event(
                            LogType.STATUS, message="Agent run completed successfully"
                        )
                        break
                    elif decision.lower() in ["m", "modify"]:
                        # Get additional instructions
                        instructions = await asyncio.wait_for(
                            run_info.agent.input_manager.decision_queue.get(),
                            timeout=30.0,
                        )
                        run_info.set_status(RunStatus.RUNNING)
                        await run_info.add_log_event(
                            LogType.STATUS,
                            message=f"Resuming with modifications: {instructions}",
                        )
                        # Simulate brief work
                        await asyncio.sleep(2)
                        await run_info.add_log_event(
                            LogType.STATUS, message="Modifications complete"
                        )
                        # Loop back to await decision again

                except asyncio.TimeoutError:
                    run_info.set_status(RunStatus.COMPLETED)
                    await run_info.add_log_event(
                        LogType.STATUS, message="Auto-completed after timeout"
                    )
                    break

        except asyncio.CancelledError:
            run_info.set_status(RunStatus.STOPPED)
            await run_info.add_log_event(
                LogType.STATUS, message="Agent run stopped by user"
            )
            raise
        except Exception as e:
            run_info.set_status(RunStatus.ERROR, str(e))
            await run_info.add_log_event(
                LogType.ERROR, error=str(e), message="Agent run failed"
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
        await run_info.add_log_event(
            LogType.STATUS, message="Agent run stopped by user"
        )

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
        await run_info.add_log_event(LogType.USER_INPUT, message=message)

        return True

    async def send_decision(
        self, run_id: str, decision: str, additional_instructions: Optional[str] = None
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

        if decision.lower() in ["m", "modify"] and additional_instructions:
            await run_info.agent.input_manager.decision_queue.put(
                additional_instructions
            )

        await run_info.add_log_event(
            LogType.USER_DECISION,
            decision=SendDecisionRequest(
                decision=DecisionType(decision),
                additional_instructions=additional_instructions,
            ),
        )

        if decision.lower() in ["d", "done"]:
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

        # Use Pydantic's model_dump to convert to dictionary
        state_dict = run_info.agent.agent_state.model_dump(mode="json")

        return state_dict
