"""Vector store operations for Supabase pgvector with graceful fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add backend to path for imports
current_file = Path(__file__).resolve()
backend_path = Path("/app")
if not (backend_path / "app").exists():
    # Try to find backend in parent directories
    for parent in current_file.parents:
        candidate = parent / "backend"
        if candidate.exists():
            backend_path = candidate
            break

if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from supabase import Client
    from app.supabase_client import get_supabase_client
except ImportError:
    # Graceful fallback
    Client = None
    def get_supabase_client():
        raise ImportError("Supabase client not available")


def store_embedding(
    supabase: Client | None,
    appraisal_id: str,
    content_type: str,
    content_text: str,
    embedding: list[float],
    pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Store embedding in Supabase appraisal_embeddings table.
    
    Args:
        supabase: Supabase client (if None, gets from settings)
        appraisal_id: UUID of the appraisal
        content_type: Type of content ('metadata', 'notes', 'vision_summary', 'risk_flags')
        content_text: The text content that was embedded
        embedding: The embedding vector (1536 dimensions)
        pipeline_run_id: Optional pipeline run ID
        
    Returns:
        Dictionary with stored embedding record
        
    Raises:
        RuntimeError: If storage fails
    """
    if supabase is None:
        supabase = get_supabase_client()
    
    try:
        result = (
            supabase.table("appraisal_embeddings")
            .insert({
                "appraisal_id": appraisal_id,
                "pipeline_run_id": pipeline_run_id,
                "content_type": content_type,
                "content_text": content_text,
                "embedding": embedding,
            })
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception as e:
        raise RuntimeError(f"Failed to store embedding: {str(e)}") from e


def search_similar(
    supabase: Client | None,
    query_embedding: list[float],
    limit: int = 5,
    match_threshold: float = 0.7,
    content_types: list[str] | None = None,
    include_outcomes: bool = True,
) -> list[dict[str, Any]]:
    """
    Search for similar appraisals using vector similarity with graceful fallback.
    
    Args:
        supabase: Supabase client (if None, gets from settings)
        query_embedding: The query embedding vector (1536 dimensions)
        limit: Maximum number of results to return
        match_threshold: Minimum similarity score (0.0 to 1.0)
        content_types: Optional list of content types to filter by
        include_outcomes: If True, includes appraisal outcomes (risk flags, decisions, etc.)
        
    Returns:
        List of similar appraisal embeddings with similarity scores.
        Returns empty list on failure (graceful degradation).
    """
    if supabase is None:
        try:
            supabase = get_supabase_client()
        except Exception:
            # Graceful fallback: return empty list if client unavailable
            return []
    
    try:
        # Try enriched function first if outcomes requested
        if include_outcomes:
            try:
                result = supabase.rpc(
                    "match_appraisals_with_outcomes",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": match_threshold,
                        "match_count": limit,
                        "content_types": content_types or [],
                    }
                ).execute()
                
                # Transform results to match expected format
                if result.data:
                    transformed = []
                    for item in result.data:
                        transformed.append({
                            "id": None,
                            "appraisal_id": item.get("appraisal_id"),
                            "content_type": item.get("content_type"),
                            "content_text": item.get("content_text"),
                            "similarity": item.get("similarity"),
                            "metadata_json": item.get("metadata_json"),
                            "historical_outcome": item.get("latest_run_outputs"),
                        })
                    return transformed
            except Exception as e:
                # If enriched function doesn't exist, fall back to basic function
                error_str = str(e).lower()
                if any(indicator in error_str for indicator in [
                    "pgrst202", 
                    "could not find the function",
                    "404",
                    "not found",
                    "function does not exist"
                ]):
                    pass  # Fall through to basic function
                else:
                    # Other errors: graceful fallback
                    return []
        
        # Use basic function (fallback or when outcomes not requested)
        result = supabase.rpc(
            "match_appraisal_embeddings",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": limit,
                "content_types": content_types or [],
            }
        ).execute()
        
        return result.data if result.data else []
    except Exception:
        # Graceful degradation: if RAG search fails, return empty list
        # Pipeline continues without RAG context
        return []


def get_embeddings_for_appraisal(
    supabase: Client | None,
    appraisal_id: str,
) -> list[dict[str, Any]]:
    """
    Get all embeddings for a specific appraisal.
    
    Args:
        supabase: Supabase client (if None, gets from settings)
        appraisal_id: UUID of the appraisal
        
    Returns:
        List of embedding records for the appraisal. Returns empty list on failure.
    """
    if supabase is None:
        try:
            supabase = get_supabase_client()
        except Exception:
            return []
    
    try:
        result = (
            supabase.table("appraisal_embeddings")
            .select("*")
            .eq("appraisal_id", appraisal_id)
            .execute()
        )
        return result.data if result.data else []
    except Exception:
        # Graceful fallback
        return []
