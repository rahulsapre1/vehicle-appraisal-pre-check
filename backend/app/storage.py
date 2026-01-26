from __future__ import annotations

import mimetypes
import os

from supabase import Client

from app.settings import get_settings


def _guess_ext(content_type: str | None, filename: str | None) -> str:
    """Guess file extension from content type or filename."""
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    if content_type:
        ext = mimetypes.guess_extension(content_type)
        if ext:
            return ext.lstrip(".")
    return "bin"


def upload_artifact_bytes(
    supabase: Client,
    appraisal_id: str,
    artifact_id: str,
    content: bytes,
    content_type: str | None,
    filename: str | None,
) -> str:
    """
    Upload artifact bytes to Supabase storage.
    
    Args:
        supabase: Supabase client
        appraisal_id: Appraisal UUID
        artifact_id: Artifact UUID
        content: File content as bytes
        content_type: MIME type
        filename: Original filename (optional)
        
    Returns:
        Storage path of uploaded file
    """
    settings = get_settings()
    ext = _guess_ext(content_type, filename)
    storage_path = f"appraisals/{appraisal_id}/{artifact_id}.{ext}"

    # NOTE: Some versions of the Supabase Python client can mis-handle non-string values
    # in file_options, so we only pass the content-type here
    supabase.storage.from_(settings.supabase_storage_bucket).upload(
        path=storage_path,
        file=content,
        file_options={
            "content-type": content_type or "application/octet-stream",
        },
    )
    return storage_path


def create_signed_url(supabase: Client, storage_path: str, expires_in_seconds: int | None = None) -> str:
    """
    Create a short-lived signed URL for private artifact access.
    
    Args:
        supabase: Supabase client
        storage_path: Path to the file in storage
        expires_in_seconds: URL expiration time. Defaults to SIGNED_URL_EXPIRATION env var
                           or 3600 (1 hour) for production, 600 (10 min) for development.
    
    Returns:
        Signed URL string
    """
    # Default expiration: longer for production (Render services may spin down)
    if expires_in_seconds is None:
        # Check env var first, then use smart defaults
        env_expiration = os.getenv("SIGNED_URL_EXPIRATION")
        if env_expiration:
            expires_in_seconds = int(env_expiration)
        else:
            # Production: 1 hour (Render free tier spins down after 15 min, but URLs should last longer)
            # Development: 10 minutes
            is_production = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod") or \
                          os.getenv("RENDER") is not None  # Render sets this env var
            expires_in_seconds = 3600 if is_production else 600
    
    settings = get_settings()
    res = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
        storage_path,
        expires_in_seconds,
    )
    # supabase-py returns dict with 'signedURL'
    if isinstance(res, dict):
        return res.get("signedURL") or res.get("signed_url")
    return str(res)
