"""
FastAPI application for the Bro agent.

Provides HTTP endpoints for managing agent runs, streaming logs,
and interacting with running agents.
"""

import json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from typing import Dict, List
from utils.screencast import ScreencastClient
from utils.db import get_supabase
from .models import (
    CreateRunRequest,
    CreateRunResponse,
    AgentStateResponse,
    ListRunsResponse,
    LogEventDB,
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

# Global registry for screencast clients per run_id
_screencast_clients: Dict[str, ScreencastClient] = {}
_screencast_websockets: Dict[str, list[WebSocket]] = {}
_chrome_intentionally_closed: bool = False


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


@app.get("/runs", response_model=List[ListRunsResponse])
async def list_runs():
    """
    get run information from database
    """

    db = await get_supabase()
    runs = await db.table("runs").select("id, status, title, completed_at").execute()

    return runs.data


@app.post("/runs", response_model=CreateRunResponse)
async def create_run(request: CreateRunRequest):
    """
    Create a new agent run.

    Args:
        request: Run configuration

    Returns:
        Run information including run_id for tracking
    """
    global _chrome_intentionally_closed

    try:
        # Reset the Chrome closed flag when starting a new run
        _chrome_intentionally_closed = False

        run_info = await run_manager.create_run(
            user_prompt=request.user_prompt,
            url=request.url,
            max_iterations=request.max_iterations,
            take_screenshot=request.take_screenshot,
            model=request.model,
            enable_logging=request.enable_logging,
        )

        return CreateRunResponse(
            run_id=run_info.run_id,
            status=run_info.status,
            message="Run created successfully and started",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=RunStatus)
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

    return run_info.status


@app.get("/runs/{run_id}/logs/stream")
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


@app.get("/runs/{run_id}/logs", response_model=List[LogEventDB])
async def get_logs(run_id: str):
    """get logs from supabase"""
    db = await get_supabase()
    return await db.table("run_logs").select("*").eq("run_id", run_id)


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
        status="success", message="Input sent to agent successfully"
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

    return StopRunResponse(status=RunStatus.STOPPED, message="Run stopped successfully")


@app.post("/browser/close", response_model=CloseBrowserResponse)
async def close_browser():
    """
    Close the Chrome browser subprocess.

    This terminates the Chrome process that was started via CDP.
    This is different from stopping a run - it actually closes the browser window.

    Returns:
        Confirmation of browser closure
    """
    global _chrome_intentionally_closed

    try:
        from bro.utils.use_cdp import close_chrome

        # Set flag to stop screencast reconnection attempts
        _chrome_intentionally_closed = True

        # Close all active screencast clients
        for run_id in list(_screencast_clients.keys()):
            client = _screencast_clients[run_id]
            await client.stop_screencast()
            await client.close()
            del _screencast_clients[run_id]

        # Close all WebSocket connections with a special message
        for run_id in list(_screencast_websockets.keys()):
            for ws in _screencast_websockets[run_id]:
                try:
                    await ws.send_json(
                        {
                            "type": "chrome_closed",
                            "message": "Chrome browser has been closed",
                        }
                    )
                    await ws.close(code=1000, reason="Chrome closed")
                except Exception:
                    pass
            del _screencast_websockets[run_id]

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


@app.websocket("/ws/screencast/{run_id}")
async def websocket_screencast(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for streaming CDP screencast frames.

    Connects to Chrome via CDP and streams base64-encoded JPEG frames
    to the frontend at ~60 FPS.

    Args:
        websocket: WebSocket connection
        run_id: Run identifier (currently unused, for future multi-agent support)
    """
    global _chrome_intentionally_closed

    await websocket.accept()
    print(f"🎥 WebSocket client connected for screencast (run_id: {run_id})")

    # Check if Chrome was intentionally closed
    if _chrome_intentionally_closed:
        await websocket.send_json(
            {"type": "chrome_closed", "message": "Chrome browser has been closed"}
        )
        await websocket.close(code=1000, reason="Chrome closed")
        return

    # Register this websocket for the run_id
    if run_id not in _screencast_websockets:
        _screencast_websockets[run_id] = []
    _screencast_websockets[run_id].append(websocket)

    try:
        # Check if screencast client already exists for this run
        if run_id not in _screencast_clients:
            try:
                print(f"📡 Creating CDP screencast client for run_id: {run_id}")

                # Create and connect CDP client
                client = ScreencastClient()
                await client.connect()

                # Define frame callback that broadcasts to all connected websockets
                async def broadcast_frame(frame_data: Dict):
                    """Broadcast frame to all connected WebSocket clients for this run."""
                    disconnected = []
                    for ws in _screencast_websockets.get(run_id, []):
                        try:
                            await ws.send_json(
                                {
                                    "type": "frame",
                                    "data": frame_data["data"],  # Base64-encoded JPEG
                                    "metadata": frame_data.get("metadata", {}),
                                }
                            )
                        except Exception as e:
                            print(f"❌ Error sending frame to websocket: {e}")
                            disconnected.append(ws)

                    # Remove disconnected websockets
                    for ws in disconnected:
                        if run_id in _screencast_websockets:
                            _screencast_websockets[run_id].remove(ws)

                # Start screencast with 10 FPS (every 6th frame at 60Hz)
                await client.start_screencast(
                    frame_callback=broadcast_frame,
                    quality=80,
                    every_nth_frame=1,
                    max_width=1280,
                    max_height=720,
                )

                _screencast_clients[run_id] = client
                print(f"✅ Screencast client started for run_id: {run_id}")

            except Exception as e:
                error_msg = f"Failed to initialize CDP screencast: {str(e)}"
                print(f"❌ {error_msg}")
                import traceback

                traceback.print_exc()
                await websocket.close(code=1011, reason=error_msg[:100])
                return

        # Keep websocket alive and handle incoming input messages
        while True:
            try:
                # Receive messages from frontend
                message = await websocket.receive_text()

                # Parse incoming messages for user input
                try:
                    data = json.loads(message)

                    client = _screencast_clients.get(run_id)
                    if not client:
                        continue

                    match data.get("type"):
                        case "input":
                            action = data.get("action")
                            match action:
                                case "click":
                                    x = data.get("x")
                                    y = data.get("y")
                                    button = data.get("button", "left")
                                    if x is not None and y is not None:
                                        await client.dispatch_mouse_click(x, y, button)
                                case "keypress":
                                    key = data.get("key")
                                    text = data.get("text", "")
                                    if key:
                                        await client.dispatch_key_event(key, text)
                                case "scroll":
                                    x = data.get("x", 0)
                                    y = data.get("y", 0)
                                    delta_y = data.get("deltaY", 0)
                                    await client.dispatch_scroll(x, y, delta_y)
                                case _:
                                    pass
                        case "navigation":
                            action = data.get("action")
                            match action:
                                case "back":
                                    await client.navigate_back()
                                case "reload":
                                    await client.reload_page()
                                case "url":  # update url
                                    # update agent state, then update the current url. DO
                                    run_info = await run_manager.get_run(run_id=run_id)
                                    url = action.get("url", "")
                                    await client.update_url(url)
                                    await run_info.agent.agent_state.update_tab_state(
                                        url
                                    )

                except json.JSONDecodeError:
                    # Ignore non-JSON messages (ping/pong)
                    pass

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        print(f"🎥 WebSocket client disconnected (run_id: {run_id})")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Cleanup
        if run_id in _screencast_websockets:
            if websocket in _screencast_websockets[run_id]:
                _screencast_websockets[run_id].remove(websocket)

            # Clean up empty websocket list, but keep screencast client running
            # The screencast client will be cleaned up when the run ends or browser closes
            if not _screencast_websockets[run_id]:
                del _screencast_websockets[run_id]
                print(
                    f"📡 All websockets disconnected for run_id: {run_id}, but keeping screencast client alive"
                )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bro.api.main:app", host="0.0.0.0", port=8000, reload=True)
