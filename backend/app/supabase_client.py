from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.settings import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Get Supabase client singleton instance.
    
    Uses LRU cache to ensure only one client instance is created.
    Configured with connection pooling for Render free tier.
    """
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key
    )
