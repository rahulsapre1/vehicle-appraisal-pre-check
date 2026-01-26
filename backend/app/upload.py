from __future__ import annotations

import hashlib
import io
import os
import uuid
from typing import Iterable

from fastapi import HTTPException, UploadFile
from PIL import Image
from pillow_heif import register_heif_opener

from app.validation import validate_image_content

# Register HEIF opener for HEIC/HEIF support
register_heif_opener()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",  # Support both jpg and jpeg
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


def normalize_content_type(content_type: str | None) -> str | None:
    """Normalize content type for consistent handling. Converts image/jpg to image/jpeg."""
    if not content_type:
        return None
    if content_type.lower() == "image/jpg":
        return "image/jpeg"
    return content_type


def enforce_photo_limits(photos: list[UploadFile]) -> None:
    """Enforce photo count limits (1-8 photos)."""
    if not photos:
        raise HTTPException(status_code=400, detail="At least one photo is required.")
    if len(photos) > 8:
        raise HTTPException(status_code=400, detail="Max 8 photos allowed.")


def enforce_total_size(files: Iterable[UploadFile], max_total_bytes: int = 50 * 1024 * 1024) -> None:
    """Enforce total upload size limit (default 50MB)."""
    total = 0
    for f in files:
        fileobj = getattr(f, "file", None)
        if fileobj is not None and hasattr(fileobj, "seek") and hasattr(fileobj, "tell"):
            pos = fileobj.tell()
            fileobj.seek(0, os.SEEK_END)
            size = fileobj.tell()
            fileobj.seek(pos)
        else:
            blob = f.file.read()
            size = len(blob)
            f.file.seek(0)
        total += size
        if total > max_total_bytes:
            raise HTTPException(status_code=400, detail="Total upload size exceeds 50MB.")


def validate_content_types(files: Iterable[UploadFile]) -> None:
    """Validate content types and actual file content."""
    for f in files:
        normalized_type = normalize_content_type(f.content_type)
        
        if normalized_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported content_type: {f.content_type}")
        
        try:
            f.file.seek(0)
            content = f.file.read()
            f.file.seek(0)
            
            is_valid, error_msg = validate_image_content(content, normalized_type)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Image validation failed: {error_msg}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to validate image: {str(e)}")


def normalize_image_bytes(content: bytes, content_type: str | None) -> tuple[bytes, str]:
    """
    If HEIC/HEIF, convert to JPEG bytes for OpenAI-friendly processing/storage.
    Otherwise, return as-is.
    """
    normalized_type = normalize_content_type(content_type)
    if normalized_type not in {"image/heic", "image/heif"}:
        return content, normalized_type or "application/octet-stream"
    
    # Convert HEIC/HEIF to JPEG
    try:
        img = Image.open(io.BytesIO(content))
        # Convert to RGB if necessary (HEIC might be in different color space)
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=95)
        return output.getvalue(), "image/jpeg"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to convert HEIC/HEIF to JPEG: {str(e)}")


def validate_photos_for_duplicates(photos: list[UploadFile]) -> None:
    """Check for duplicate photos using image hashing."""
    from app.validation import calculate_image_hash
    
    seen_hashes = set()
    for photo in photos:
        photo.file.seek(0)
        content = photo.file.read()
        photo.file.seek(0)
        
        img_hash = calculate_image_hash(content)
        if img_hash in seen_hashes:
            raise HTTPException(status_code=400, detail="Duplicate photo detected.")
        seen_hashes.add(img_hash)


def new_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def generate_short_id_from_db(supabase) -> str:
    """
    Generate a unique 4-character short ID using PostgreSQL function.
    Falls back to client-side generation if DB call fails.
    """
    try:
        result = supabase.rpc("generate_short_id").execute()
        if result.data:
            return result.data
    except Exception:
        pass
    
    # Fallback: client-side generation (less reliable but works)
    import random
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choice(chars) for _ in range(4))
