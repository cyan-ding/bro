import os
import json
from pathlib import Path
from typing import Optional, List

from api.models import LogEvent, RunState
from api.run_info import RunInfo
from utils.env_loader import load_env_files
from supabase import AsyncClient, create_async_client

_supabase_client: Optional[AsyncClient] = None


def get_storage_mode() -> str:
    """Get storage mode from settings or env var"""
    from utils.config import UserSettings
    settings = UserSettings.load()
    return settings.storage_mode


def get_local_storage_path() -> Path:
    """Get the local storage directory"""
    storage_dir = Path.home() / ".bro" / "data"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


async def get_supabase() -> AsyncClient:
    load_env_files()
    global _supabase_client

    if _supabase_client is None:
        from utils.config import UserSettings
        settings = UserSettings.load()

        supabase_url = None
        supabase_key = None

        if settings and settings.supabase_url and settings.supabase_api_key:
            supabase_url = settings.supabase_url
            supabase_key = settings.supabase_api_key
        else:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_API_KEY")

        _supabase_client = await create_async_client(supabase_url, supabase_key)
    return _supabase_client


async def get_local_run(run_id: str) -> Optional[RunState]:
    """Get run from local storage"""
    storage_path = get_local_storage_path()
    run_file = storage_path / f"{run_id}.json"

    if not run_file.exists():
        return None

    try:
        with open(run_file, "r") as f:
            data = json.load(f)
            return RunState(**data)
    except Exception as e:
        print(f"Error reading local run: {e}")
        return None


async def get_local_logs(run_id: str) -> List[dict]:
    """Get logs from local storage"""
    storage_path = get_local_storage_path()
    log_file = storage_path / f"{run_id}_logs.jsonl"

    if not log_file.exists():
        return []

    logs = []
    try:
        with open(log_file, "r") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
    except Exception as e:
        print(f"Error reading local logs: {e}")

    return logs


async def list_local_runs() -> List[dict]:
    """List all runs from local storage"""
    storage_path = get_local_storage_path()
    runs = []

    for run_file in storage_path.glob("*.json"):
        if not run_file.name.endswith("_logs.jsonl"):
            try:
                with open(run_file, "r") as f:
                    data = json.load(f)
                    runs.append({
                        "id": data["id"],
                        "status": data["status"],
                        "title": data.get("title"),
                        "completed_at": data.get("completed_at")
                    })
            except Exception as e:
                print(f"Error reading {run_file}: {e}")

    return runs


async def delete_local_run(run_id: str) -> bool:
    """Delete a run from local storage"""
    storage_path = get_local_storage_path()
    run_file = storage_path / f"{run_id}.json"
    log_file = storage_path / f"{run_id}_logs.jsonl"

    try:
        # Delete run file
        if run_file.exists():
            run_file.unlink()

        # Delete log file
        if log_file.exists():
            log_file.unlink()

        return True
    except Exception as e:
        print(f"Error deleting local run: {e}")
        return False


async def save_logs(run_id: str, log_event: LogEvent):
    storage_mode = get_storage_mode()

    if storage_mode == "local":
        storage_path = get_local_storage_path()
        log_file = storage_path / f"{run_id}_logs.jsonl"

        try:
            with open(log_file, "a") as f:
                json.dump(log_event.model_dump(mode="json"), f)
                f.write("\n")
        except Exception as e:
            print(f"Warning, Failed to save logs locally: {e}")
    else:
        try:
            supabase = await get_supabase()

            await (
                supabase.table("run_logs")
                .insert({"run_id": run_id, **log_event.model_dump(mode="json")})
                .execute()
            )
        except Exception as e:
            print("Warning, Failed to save logs: ", e)


async def save_run_state(run_info: RunInfo):
    storage_mode = get_storage_mode()

    run_state = RunState(
        id=run_info.run_id,
        title=run_info.title,
        status=run_info.status,
        user_prompt=run_info.user_prompt,
        url=run_info.url,
        max_iterations=run_info.max_iterations,
        model=run_info.agent.model if run_info.agent else "",
        current_iteration=run_info.current_iteration,
        error_message=run_info.error_message,
        created_at=run_info.created_at,
        completed_at=run_info.completed_at,
        metadata=run_info.agent.agent_state.model_dump() if run_info.agent else {},
    )

    if storage_mode == "local":
        storage_path = get_local_storage_path()
        run_file = storage_path / f"{run_info.run_id}.json"

        try:
            with open(run_file, "w") as f:
                json.dump(run_state.model_dump(mode="json"), f, indent=2, default=str)
        except Exception as e:
            print(f"Warning, Failed to save run state locally: {e}")
    else:
        try:
            supabase = await get_supabase()

            await (
                supabase.table("runs")
                .upsert(run_state.model_dump(mode="json"), on_conflict="id")
                .execute()
            )
        except Exception as e:
            print("Warning, Failed to save run state: ", e)
