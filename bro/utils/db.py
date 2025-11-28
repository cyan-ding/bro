from supabase import create_async_client, AsyncClient
from typing import Optional
from dotenv import load_dotenv
import os

_supabase_client: Optional[AsyncClient] = None


async def get_supabase() -> AsyncClient:
    load_dotenv()
    global _supabase_client

    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        _supabase_client = await create_async_client(supabase_url, supabase_key)
    return _supabase_client
