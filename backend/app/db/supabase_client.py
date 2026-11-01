"""
Supabase client — server-side only (uses service role key).
Never expose this client or its credentials to the frontend.
"""
from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase admin client."""
    global _supabase_client
    if _supabase_client is None:
        url = settings.SUPABASE_URL or "https://placeholder-project.supabase.co"
        key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "placeholder-key"
        _supabase_client = create_client(url, key)
    return _supabase_client

