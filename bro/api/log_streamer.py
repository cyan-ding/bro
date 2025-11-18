"""
Log streaming functionality for Server-Sent Events (SSE).

Provides real-time log streaming from agent runs to API clients
using Server-Sent Events.
"""

import asyncio
import json
from typing import AsyncGenerator
from .run_manager import RunInfo
from .models import LogEvent, RunStatus


async def stream_logs(run_info: RunInfo) -> AsyncGenerator[str, None]:
    """
    Stream log events from an agent run as Server-Sent Events.

    Continuously yields log events from the run's log queue in SSE format.
    Completes when the run finishes or encounters an error.

    Args:
        run_info: Information about the run to stream logs from

    Yields:
        SSE-formatted strings containing log event data
    """
    try:
        while True:
            # Check if run is complete
            if run_info.status in [
                RunStatus.COMPLETED,
                RunStatus.STOPPED,
                RunStatus.ERROR,
            ]:
                # Drain any remaining logs
                while not run_info.log_queue.empty():
                    try:
                        event = await asyncio.wait_for(
                            run_info.log_queue.get(), timeout=0.1
                        )
                        yield format_sse(event)
                    except asyncio.TimeoutError:
                        break

                # Send final status event
                final_event = LogEvent(
                    timestamp=run_info.completed_at.isoformat()
                    if run_info.completed_at else "",
                    iteration=run_info.current_iteration,
                    event_type="final_status",
                    message="Run Complete",
                )
                yield format_sse(final_event)
                break

            # Wait for next log event
            try:
                event = await asyncio.wait_for(run_info.log_queue.get(), timeout=1.0)
                yield format_sse(event)
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent connection timeout
                continue

    except asyncio.CancelledError:
        # Client disconnected
        pass
    except Exception as e:
        # Send error event and close
        error_event = LogEvent(
            timestamp="",
            iteration=run_info.current_iteration,
            event_type="error",
            error=str(e),
        )
        yield format_sse(error_event)


def format_sse(event: LogEvent) -> str:
    """
    Format a log event as an SSE message.

    Args:
        event: LogEvent to format

    Returns:
        SSE-formatted string
    """
    event_dict = event.model_dump()
    return {"event": "message", "data": json.dumps(event_dict)}
