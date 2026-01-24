"""
FastAPI application for the Bro agent.

Provides HTTP endpoints for managing agent runs, streaming logs,
and interacting with running agents.
"""

import asyncio
import sys

from api.run_info import RunInfo
from utils.config import UserSettings

# fix for windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from utils.db import get_supabase
from utils.screencast import ScreencastClient
from utils.use_cdp import use_cdp

from .log_streamer import stream_logs
from .models import (
    AgentStateResponse,
    CloseBrowserResponse,
    CreateRunRequest,
    CreateRunResponse,
    ListRunsResponse,
    LogEventDB,
    RunState,
    RunStatus,
    SendDecisionRequest,
    SendDecisionResponse,
    SendInputRequest,
    SendInputResponse,
    StopRunResponse,
)
from .run_manager import RunManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """run before api starts"""
    use_cdp()

    yield


# Initialize FastAPI app
app = FastAPI(
    title="Bro Agent API",
    description="API for managing Bro web automation agent runs",
    version="0.1.0",
    # lifespan=lifespan,
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
run_manager = RunManager()

# Global registry for screencast client and websocket
_screencast_client: Optional[ScreencastClient] = None
_screencast_websocket: Optional[WebSocket] = None
_chrome_intentionally_closed: bool = False


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Bro Agent API",
        "version": "0.1.0",
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
    get run information from database or local storage
    """
    from utils.db import get_storage_mode, list_local_runs

    storage_mode = get_storage_mode()

    if storage_mode == "local":
        runs = await list_local_runs()
        return runs
    else:
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

        use_cdp()

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


@app.get("/runs/{run_id}/status", response_model=RunStatus)
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
        try:
            pulled_run = await get_run(run_id)
            run_info = RunInfo(
                run_id=run_id,
                agent=None,
                max_iterations=pulled_run.max_iterations,
                user_prompt=pulled_run.user_prompt,
                title=pulled_run.title,
            )
            run_info.set_status(pulled_run.status)
            await run_manager.set_run(run_id, run_info)
        except Exception:
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


@app.get("/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str) -> RunState:
    """get the data of one run"""
    from utils.db import get_storage_mode, get_local_run

    storage_mode = get_storage_mode()

    if storage_mode == "local":
        run_data = await get_local_run(run_id)
        if not run_data:
            raise HTTPException(status_code=404, detail="Run not found")
        return run_data
    else:
        supabase = await get_supabase()
        run_data = await supabase.table("runs").select("*").eq("id", run_id).execute()

        if not run_data.data:
            raise HTTPException(status_code=404, detail="Run not found")

        return run_data.data[0]


@app.get("/runs/{run_id}/logs", response_model=List[LogEventDB])
async def get_logs(run_id: str):
    """get logs from supabase or local storage"""
    from utils.db import get_storage_mode, get_local_logs

    storage_mode = get_storage_mode()

    if storage_mode == "local":
        logs = await get_local_logs(run_id)
        return logs
    else:
        db = await get_supabase()
        result = await db.table("run_logs").select("*").eq("run_id", run_id).execute()
        return result.data


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


@app.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    """
    Delete a run from storage.

    Args:
        run_id: Run identifier

    Returns:
        Confirmation of deletion
    """
    from utils.db import get_storage_mode, delete_local_run

    storage_mode = get_storage_mode()

    try:
        if storage_mode == "local":
            success = await delete_local_run(run_id)
            if not success:
                raise HTTPException(
                    status_code=404,
                    detail="Run not found or could not be deleted"
                )
        else:
            supabase = await get_supabase()

            # Delete run logs first (foreign key constraint)
            await supabase.table("run_logs").delete().eq("run_id", run_id).execute()

            # Delete the run
            result = await supabase.table("runs").delete().eq("id", run_id).execute()

            if not result.data:
                raise HTTPException(
                    status_code=404,
                    detail="Run not found"
                )

        return {"status": "success", "message": "Run deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting run: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete run: {str(e)}"
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
    global _chrome_intentionally_closed, _screencast_client, _screencast_websocket

    try:
        from bro.utils.use_cdp import close_chrome

        # Set flag to stop screencast reconnection attempts
        _chrome_intentionally_closed = True

        # Close active screencast client
        if _screencast_client:
            await _screencast_client.stop_screencast()
            await _screencast_client.close()
            _screencast_client = None

        # Close WebSocket connection with a special message
        if _screencast_websocket:
            try:
                await _screencast_websocket.send_json(
                    {
                        "type": "chrome_closed",
                        "message": "Chrome browser has been closed",
                    }
                )
                await _screencast_websocket.close(code=1000, reason="Chrome closed")
            except Exception:
                pass
            _screencast_websocket = None

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


@app.websocket("/ws/screencast")
async def websocket_screencast(websocket: WebSocket):
    """
    WebSocket endpoint for streaming CDP screencast frames.

    Connects to Chrome via CDP and streams base64-encoded JPEG frames
    to the frontend at ~60 FPS.

    Args:
        websocket: WebSocket connection
    """
    global _chrome_intentionally_closed, _screencast_client, _screencast_websocket

    await websocket.accept()

    # Check if Chrome was intentionally closed
    if _chrome_intentionally_closed:
        await websocket.send_json(
            {"type": "chrome_closed", "message": "Chrome browser has been closed"}
        )
        await websocket.close(code=1000, reason="Chrome closed")
        return

    use_cdp()  # naive solution but works because its idempotent
    # Close existing websocket if one exists
    if _screencast_websocket:
        try:
            await _screencast_websocket.close(code=1001, reason="New connection")
        except Exception:
            pass

    # Register this websocket
    _screencast_websocket = websocket

    try:
        # Check if screencast client already exists
        if _screencast_client is None:
            try:
                # Create and connect CDP client
                client = ScreencastClient()
                await client.connect()

                # Define frame callback that sends to the connected WebSocket client
                async def broadcast_frame(frame_data: Dict):
                    """Send frame to the connected WebSocket client."""
                    global _screencast_websocket
                    if _screencast_websocket:
                        try:
                            await _screencast_websocket.send_json(
                                {
                                    "type": "frame",
                                    "data": frame_data["data"],  # Base64-encoded JPEG
                                    "metadata": frame_data.get("metadata", {}),
                                }
                            )
                        except Exception as e:
                            print(f"❌ Error sending frame to websocket: {e}")
                            _screencast_websocket = None

                await client.start_screencast(
                    frame_callback=broadcast_frame,
                    quality=80,
                    every_nth_frame=1,
                    max_width=1280,
                    max_height=720,
                )

                _screencast_client = client

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

                    match data.get("type"):
                        case "input":
                            action = data.get("action")
                            match action:
                                case "click":
                                    x = data.get("x")
                                    y = data.get("y")
                                    button = data.get("button", "left")
                                    if x is not None and y is not None:
                                        await _screencast_client.dispatch_mouse_click(
                                            x, y, button
                                        )
                                case "keypress":
                                    key = data.get("key")
                                    text = data.get("text", "")
                                    if key:
                                        await _screencast_client.dispatch_key_event(
                                            key, text
                                        )
                                case "scroll":
                                    x = data.get("x", 0)
                                    y = data.get("y", 0)
                                    delta_y = data.get("deltaY", 0)
                                    await _screencast_client.dispatch_scroll(
                                        x, y, delta_y
                                    )
                                case _:
                                    pass
                        case "navigation":
                            action = data.get("action")
                            match action:
                                case "back":
                                    await _screencast_client.navigate_back()
                                case "reload":
                                    await _screencast_client.reload_page()
                                case "url":  # update url
                                    url = data.get("url", "")
                                    await _screencast_client.update_url(url)

                except json.JSONDecodeError:
                    # Ignore non-JSON messages (ping/pong)
                    pass

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        print("🎥 WebSocket client disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Cleanup
        _screencast_websocket = None

"""
these settings endpoints are not actively used, the desktop directly interacts with the filesystem
"""

@app.post("/models/validate")
async def get_valid_models():
    """
    Get valid models based on environment variables.
    Uses LiteLLM's get_valid_models() to check which models are accessible
    with the current API keys.

    Returns:
        Dictionary with list of valid model names
    """
    import os
    from pathlib import Path
    from litellm import get_valid_models
    from utils.env_loader import load_env_files


    user_env = Path.home() / ".bro" / ".env"
    local_env = Path(__file__).parent.parent.parent / ".env" # lwk not sure why this fixes a bug but it does :sob:

    env_paths = [user_env] + ([local_env] if local_env.exists() else [])
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key = line.split("=", 1)[0].strip()
                        # Clear all keys that were previously defined in .env files
                        # This ensures removed keys don't persist from previous loads
                        os.environ.pop(key, None)

    # Load environment variables fresh (~/.bro/.env)
    load_env_files()

    try:
        valid_models = get_valid_models(check_provider_endpoint=True)
        return {"models": valid_models}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get valid models: {str(e)}"
        )


@app.get("/settings")
async def get_settings():
    settings = UserSettings.load()
    if not settings:
        raise HTTPException(status_code=404, detail="User settings not found")
    return settings.model_dump(mode="json")


@app.put("/settings", response_model=UserSettings)
async def update_settings(request: UserSettings):
    request.save()
    return request


if __name__ == "__main__":
    # MUST set event loop policy before importing uvicorn for Windows
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    # Note: reload=False on Windows to ensure event loop policy is respected
    # The reloader spawns subprocesses that create event loops before policy is set
    uvicorn.run("bro.api.main:app", host="0.0.0.0", port=8000, reload=False)
