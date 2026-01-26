"""
Validation utilities for security and data quality improvements.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image

try:
    import imagehash
except ImportError:
    imagehash = None  # Will handle gracefully if not installed

VALIDATION_VERSION = "2026-01-23-relaxed-mime-match"

# VIN checksum weights (position-based)
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
VIN_VALUES = {
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
    'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9
}


def validate_vin_checksum(vin: str) -> bool:
    """Validate VIN checksum digit (9th character). Returns True if checksum is valid."""
    if len(vin) != 17:
        return False
    
    vin_upper = vin.upper()
    
    # Calculate checksum
    total = 0
    for i, char in enumerate(vin_upper):
        if i == 8:  # Skip checksum digit position
            continue
        if char not in VIN_VALUES:
            return False
        total += VIN_VALUES[char] * VIN_WEIGHTS[i]
    
    # Get check digit
    check_digit = total % 11
    if check_digit == 10:
        expected = 'X'
    else:
        expected = str(check_digit)
    
    return vin_upper[8] == expected


def calculate_image_hash(image_bytes: bytes) -> str:
    """Calculate perceptual hash of an image for duplicate detection. Returns hex string."""
    if imagehash is None:
        # Fallback to SHA256 if imagehash not available
        return hashlib.sha256(image_bytes).hexdigest()
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # Use average hash for duplicate detection
        hash_value = imagehash.average_hash(img)
        return str(hash_value)
    except Exception:
        # Fallback to SHA256 on error
        return hashlib.sha256(image_bytes).hexdigest()


def validate_image_content(content: bytes, content_type: str | None) -> tuple[bool, str | None]:
    """
    Validate that file content is actually a valid image.
    Returns (is_valid, error_message).
    """
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()  # Verify it's a valid image
        
        # Check dimensions are reasonable
        img = Image.open(io.BytesIO(content))  # Reopen after verify
        width, height = img.size
        
        if width < 100 or height < 100:
            return False, "Image dimensions too small (minimum 100x100)"
        
        if width > 10000 or height > 10000:
            return False, "Image dimensions too large (maximum 10000x10000)"
        
        return True, None
        
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"


def validate_idempotency_key(key: str | None) -> tuple[bool, str | None]:
    """Validate idempotency key format (should be UUID). Returns (is_valid, error_message)."""
    if not key:
        return False, "Idempotency-Key header is required"
    
    try:
        uuid.UUID(key)
        return True, None
    except ValueError:
        return False, "Idempotency-Key must be a valid UUID format"


def validate_notes_length(notes: str | None, max_length: int = 10000) -> tuple[bool, str | None]:
    """Validate notes length. Returns (is_valid, error_message)."""
    if notes is None:
        return True, None  # Notes are optional
    
    if len(notes) > max_length:
        return False, f"Notes exceed maximum length of {max_length} characters"
    
    return True, None


def sanitize_notes(notes: str | None) -> str | None:
    """
    Sanitize notes to prevent injection attacks.
    Basic sanitization - remove null bytes and control characters.
    """
    if notes is None:
        return None
    
    # Remove null bytes and control characters (except newlines and tabs)
    sanitized = "".join(char for char in notes if ord(char) >= 32 or char in "\n\t")
    
    # Limit length
    if len(sanitized) > 10000:
        sanitized = sanitized[:10000]
    
    return sanitized
