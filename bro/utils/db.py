from supabase import create_async_client, AsyncClient
from typing import Optional
from dotenv import load_dotenv
import os
from api.models import LogEvent, RunState

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
        
        await supabase.table("run_logs").insert(
            {
                "run_id": run_id,
                **log_event.model_dump(mode="json")
            }
        ).execute()
    except Exception as e:
        print("Warning, Failed to save logs: ", e)
   
async def save_run_state(run_state: RunState):
    try:
        supabase = await get_supabase()

        await supabase.table("runs").upsert(
            run_state.model_dump(mode="json"),
            on_conflict="id"
        ).execute()
    except Exception as e:
        print("Warning, Failed to save run state: ", e)