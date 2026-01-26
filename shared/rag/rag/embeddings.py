"""Embedding generation using OpenAI with graceful fallback."""

from __future__ import annotations

import sys
from pathlib import Path

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

from openai import OpenAI

try:
    from app.settings import get_settings
except ImportError:
    # Graceful fallback if settings not available
    def get_settings():
        raise ImportError("Settings not available")


def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding using OpenAI text-embedding-ada-002.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        List of 1536 float values representing the embedding vector
        
    Raises:
        RuntimeError: If embedding generation fails
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    
    try:
        settings = get_settings()
        client = OpenAI(api_key=settings.openai_api_key)
        
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text.strip()
        )
        return response.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding: {str(e)}") from e


async def generate_embedding_async(text: str) -> list[float]:
    """
    Async version of generate_embedding.
    Wraps synchronous call in asyncio.to_thread().
    """
    import asyncio
    return await asyncio.to_thread(generate_embedding, text)
