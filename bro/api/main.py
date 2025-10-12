"""
FastAPI application for the Bro agent.

Provides HTTP endpoints for managing agent runs, streaming logs,
and interacting with running agents.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .models import (
    CreateRunRequest,
    CreateRunResponse,
    RunStatusResponse,
    AgentStateResponse,
    SendInputRequest,
    SendInputResponse,
    SendDecisionRequest,
    SendDecisionResponse,
    StopRunResponse,
    CloseBrowserResponse,
    RunStatus,
)
from .run_manager import RunManager
from .mock_run_manager import MockRunManager
from .log_streamer import stream_logs


# Set to True to use mock data for frontend testing
USE_MOCK = False

# Initialize FastAPI app
app = FastAPI(
    title="Bro Agent API",
    description="API for managing Bro web automation agent runs",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global run manager instance (mock or real based on USE_MOCK)
run_manager = MockRunManager() if USE_MOCK else RunManager()


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Bro Agent API",
        "version": "0.1.0",
        "mode": "MOCK" if USE_MOCK else "PRODUCTION",
        "endpoints": {
            "create_run": "POST /runs",
            "get_run_status": "GET /runs/{run_id}",
            "stream_logs": "GET /runs/{run_id}/logs",
            "get_agent_state": "GET /runs/{run_id}/state",
            "send_input": "POST /runs/{run_id}/input",
            "send_decision": "POST /runs/{run_id}/decision",
            "stop_run": "POST /runs/{run_id}/stop",
            "close_browser": "POST /browser/close",
        },
    }


@app.post("/runs", response_model=CreateRunResponse)
async def create_run(request: CreateRunRequest):
    """
    Create a new agent run.

    Args:
        request: Run configuration

    Returns:
        Run information including run_id for tracking
    """
    try:
        run_info = await run_manager.create_run(
            user_prompt=request.user_prompt,
            url=request.url,
            max_iterations=request.max_iterations,
            take_screenshot=request.take_screenshot,
            model=request.model,
            user_id=request.user_id,
            session_id=request.session_id,
            enable_logging=request.enable_logging,
        )

        return CreateRunResponse(
            run_id=run_info.run_id,
            session_id=run_info.session_id,
            user_id=run_info.user_id,
            status=run_info.status,
            message="Run created successfully and started",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=RunStatusResponse)
async def get_run_status(run_id: str):
    """
    Get the current status of an agent run.

    Args:
        run_id: Run identifier

    Returns:
        Current run status and progress information
    """
    run_info = await run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunStatusResponse(
        run_id=run_info.run_id,
        session_id=run_info.session_id,
        user_id=run_info.user_id,
        status=run_info.status,
        current_iteration=run_info.current_iteration,
        max_iterations=run_info.max_iterations,
        last_action=run_info.last_action,
        message=run_info.error_message if run_info.status == RunStatus.ERROR else None,
    )


@app.get("/runs/{run_id}/logs")
async def stream_run_logs(run_id: str):
    """
    Stream log events from an agent run using Server-Sent Events.

    Args:
        run_id: Run identifier

    Returns:
        SSE stream of log events
    """
    run_info = await run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")

    return EventSourceResponse(stream_logs(run_info))


@app.get("/runs/{run_id}/state", response_model=AgentStateResponse)
async def get_agent_state(run_id: str):
    """
    Get the full agent state for a run.

    Args:
        run_id: Run identifier

    Returns:
        Complete agent state including tabs, extractions, todo list, and action history
    """
    state = await run_manager.get_agent_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    return AgentStateResponse(**state)


@app.post("/runs/{run_id}/input", response_model=SendInputResponse)
async def send_input(run_id: str, request: SendInputRequest):
    """
    Send additional instructions to a running agent.

    Args:
        run_id: Run identifier
        request: Input message

    Returns:
        Confirmation of input submission
    """
    success = await run_manager.send_input(run_id, request.message)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Could not send input. Run may not exist or not be running.",
        )

    return SendInputResponse(
        run_id=run_id, status="success", message="Input sent to agent successfully"
    )


@app.post("/runs/{run_id}/decision", response_model=SendDecisionResponse)
async def send_decision(run_id: str, request: SendDecisionRequest):
    """
    Respond to an agent's completion prompt.

    Args:
        run_id: Run identifier
        request: Decision and optional additional instructions

    Returns:
        Confirmation of decision submission
    """
    success = await run_manager.send_decision(
        run_id, request.decision.value, request.additional_instructions
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Could not send decision. Run may not exist or not awaiting decision.",
        )

    return SendDecisionResponse(
        run_id=run_id,
        status="success",
        message=f"Decision '{request.decision.value}' sent to agent successfully",
    )


@app.post("/runs/{run_id}/stop", response_model=StopRunResponse)
async def stop_run(run_id: str):
    """
    Stop a running agent.

    Args:
        run_id: Run identifier
        request: Stop request (empty)

    Returns:
        Confirmation of stop action
    """
    success = await run_manager.stop_run(run_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Could not stop run. Run may not exist or already stopped.",
        )

    return StopRunResponse(
        run_id=run_id, status=RunStatus.STOPPED, message="Run stopped successfully"
    )


@app.post("/browser/close", response_model=CloseBrowserResponse)
async def close_browser():
    """
    Close the Chrome browser subprocess.

    This terminates the Chrome process that was started via CDP.
    This is different from stopping a run - it actually closes the browser window.

    Returns:
        Confirmation of browser closure
    """
    try:
        from utils.use_cdp import close_chrome

        success = close_chrome()

        if success:
            return CloseBrowserResponse(
                status="success", message="Chrome browser closed successfully"
            )
        else:
            return CloseBrowserResponse(
                status="warning",
                message="No Chrome process was tracked. Browser may have been started externally.",
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to close browser: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bro.api.main:app", host="0.0.0.0", port=8000, reload=True)
