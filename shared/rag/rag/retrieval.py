"""RAG retrieval logic for finding similar appraisals with graceful fallback."""

from __future__ import annotations

from typing import Any

from .embeddings import generate_embedding
from .vector_store import search_similar


def retrieve_similar_appraisals(
    query_text: str,
    limit: int = 5,
    match_threshold: float = 0.7,
    content_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Retrieve similar historical appraisals using RAG with comprehensive graceful fallback.
    
    This function:
    1. Generates an embedding for the query text
    2. Searches for similar embeddings in the database
    3. Returns similar appraisals with similarity scores
    
    Args:
        query_text: Text to search for (e.g., vehicle metadata + notes)
        limit: Maximum number of results
        match_threshold: Minimum similarity score (0.0 to 1.0)
        content_types: Optional list of content types to search ('metadata', 'notes', etc.)
        
    Returns:
        Dictionary with:
        - similar_appraisals: List of similar appraisals (empty on failure)
        - rag_enabled: Boolean indicating if RAG was used
        - rag_error: Error message if RAG failed (None if successful)
    """
    if not query_text or not query_text.strip():
        return {
            "similar_appraisals": [],
            "rag_enabled": False,
            "rag_error": "Empty query text"
        }
    
    try:
        # Generate embedding for query
        query_embedding = generate_embedding(query_text.strip())
        
        # Search for similar embeddings
        similar = search_similar(
            supabase=None,  # Will get from settings
            query_embedding=query_embedding,
            limit=limit,
            match_threshold=match_threshold,
            content_types=content_types,
        )
        
        return {
            "similar_appraisals": similar,
            "rag_enabled": True,
            "rag_error": None
        }
    except Exception as e:
        # Graceful degradation: if RAG fails, return empty results with error context
        # This ensures pipeline continues even if RAG is unavailable
        return {
            "similar_appraisals": [],
            "rag_enabled": False,
            "rag_error": str(e)
        }


def build_query_text_from_context(context: dict[str, Any]) -> str:
    """
    Build query text from pipeline context for RAG retrieval.
    
    Args:
        context: Pipeline context dictionary
        
    Returns:
        Query text string for embedding generation
    """
    parts = []
    
    # Extract normalized metadata
    normalized = context.get("ingest_normalize", {})
    metadata = normalized.get("normalized_metadata", {})
    
    if metadata:
        # Add vehicle information
        if metadata.get("year"):
            parts.append(f"Year: {metadata['year']}")
        if metadata.get("make"):
            parts.append(f"Make: {metadata['make']}")
        if metadata.get("model"):
            parts.append(f"Model: {metadata['model']}")
        if metadata.get("mileage") is not None:
            parts.append(f"Mileage: {metadata['mileage']}")
    
    # Add notes
    notes = normalized.get("notes", "")
    if notes and notes.strip():
        parts.append(f"Notes: {notes.strip()}")
    
    # Add vision summary if available
    vision_outputs = context.get("vision_per_image", {}).get("vision_outputs", [])
    if vision_outputs:
        damage_items = []
        for output in vision_outputs:
            extraction = output.get("extraction", {})
            damage = extraction.get("damage", [])
            for d in damage:
                if d.get("type"):
                    damage_items.append(d["type"])
        if damage_items:
            parts.append(f"Damage: {', '.join(damage_items)}")
    
    return " | ".join(parts) if parts else ""
