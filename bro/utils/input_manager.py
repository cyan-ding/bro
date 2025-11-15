"""
Input management system for Bro agent.

Provides a unified input system that routes user input to different queues
based on context (agent instructions, decisions).

@file purpose: Manages all user input routing for the Bro agent
"""

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class InputState:
    """
    Tracks what type of input is currently expected.

    Only one flag should be True at a time, indicating where the next
    input should be routed.
    """

    waiting_for_decision: bool = False  # True if waiting for done() decision


class InputManager:
    """
    Manages user input routing across different contexts.

    Routes input to appropriate queues based on current state:
    - Message queue: Agent instructions (default)
    - Decision queue: Responses to done() prompts
    """

    def __init__(self, enable_stdin: bool = True):
        """
        Initialize the input manager with queues and state.

        Args:
            enable_stdin: If True, starts stdin listener. Set to False for API/web server mode.
        """
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.decision_queue: asyncio.Queue = asyncio.Queue()
        self.state = InputState()
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        self._enable_stdin = enable_stdin

    async def start(self) -> None:
        """Start the input listener background task (only if stdin is enabled)."""
        if self._running:
            return

        self._running = True

        # Only start stdin listener if enabled (disabled for API/web server mode)
        if self._enable_stdin:
            self._listener_task = asyncio.create_task(self._input_listener())
            print(
                "🎤 Input listener started. You can send messages to the agent anytime."
            )

    async def stop(self) -> None:
        """Stop the input listener background task."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

    async def _input_listener(self) -> None:
        """
        Background task that continuously reads from stdin and routes to appropriate queue.

        Routing logic:
        - If waiting for decision: route to decision_queue
        - Otherwise: route to message_queue (agent instructions)
        """
        while self._running:
            try:
                # Read input in a non-blocking way
                user_input = await asyncio.to_thread(input, ">>> ")

                # Route based on current state
                if self.state.waiting_for_decision:
                    await self.decision_queue.put(user_input)
                else:
                    # Default: agent instruction
                    await self.message_queue.put(user_input)

            except EOFError:
                # Handle EOF gracefully
                break
            except Exception as e:
                print(f"⚠️ Input listener error: {e}")

    def clear_waiting(self) -> None:
        """Clear all waiting flags, returning to default message routing."""
        self.state.waiting_for_decision = False

    async def get_decision(self) -> str:
        """
        Wait for and return a decision response from the decision queue.

        Returns:
            The decision entered by the user
        """
        self.state.waiting_for_decision = True
        decision = await self.decision_queue.get()
        self.clear_waiting()
        return decision

    def get_messages(self) -> list[str]:
        """
        Get all pending agent instruction messages from the queue.

        Returns:
            List of pending messages (empty if none)
        """
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages
