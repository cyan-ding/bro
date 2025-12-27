import os
from typing import Optional

from api.models import LogEvent, RunState
from api.run_info import RunInfo
from dotenv import load_dotenv
from supabase import AsyncClient, create_async_client

_supabase_client: Optional[AsyncClient] = None


async def get_supabase() -> AsyncClient:
    load_dotenv()
    global _supabase_client

    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_API_KEY")

        _supabase_client = await create_async_client(supabase_url, supabase_key)
    return _supabase_client


async def save_logs(run_id: str, log_event: LogEvent):
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
    run_state = RunState(
        id=run_info.run_id,
        title=run_info.title,
        status=run_info.status,
        user_prompt=run_info.user_prompt,
        url=run_info.url,
        max_iterations=run_info.max_iterations,
        model=run_info.agent.model,
        current_iteration=run_info.current_iteration,
        error_message=run_info.error_message,
        created_at=run_info.created_at,
        completed_at=run_info.completed_at,
        metadata=run_info.agent.agent_state.model_dump(),
    )
    try:
        supabase = await get_supabase()

        await (
            supabase.table("runs")
            .upsert(run_state.model_dump(mode="json"), on_conflict="id")
            .execute()
        )
    except Exception as e:
        print("Warning, Failed to save run state: ", e)
