"""
Metadata schema validation for appraisals.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AppraisalMetadata(BaseModel):
    """Validated metadata schema for appraisals."""
    
    year: int | None = Field(None, ge=1900, le=2030, description="Vehicle year")
    make: str | None = Field(None, min_length=1, max_length=100, description="Vehicle make")
    model: str | None = Field(None, min_length=1, max_length=100, description="Vehicle model")
    trim: str | None = Field(None, max_length=100, description="Vehicle trim")
    mileage: float | None = Field(None, ge=0, le=1000000, description="Vehicle mileage in miles")
    color: str | None = Field(None, max_length=50, description="Vehicle color")
    vin: str | None = Field(None, max_length=17, description="Vehicle VIN (optional)")
    
    @field_validator('year')
    @classmethod
    def validate_year(cls, v: Any) -> int | None:
        """Validate year is reasonable."""
        if v is None:
            return None
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("Year must be an integer")
        if v < 1900 or v > 2030:
            raise ValueError("Year must be between 1900 and 2030")
        return v
    
    @field_validator('mileage')
    @classmethod
    def validate_mileage(cls, v: Any) -> float | None:
        """Validate mileage is reasonable."""
        if v is None:
            return None
        if not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (ValueError, TypeError):
                raise ValueError("Mileage must be a number")
        if v < 0:
            raise ValueError("Mileage cannot be negative")
        if v > 1000000:
            raise ValueError("Mileage cannot exceed 1,000,000")
        return float(v)
    
    @field_validator('make', 'model', 'trim', 'color')
    @classmethod
    def validate_string_fields(cls, v: Any) -> str | None:
        """Validate string fields are not empty if provided."""
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        v = v.strip()
        if len(v) == 0:
            return None
        return v
    
    class Config:
        extra = "forbid"  # Reject unknown fields


def validate_metadata(metadata_dict: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Validate metadata against schema.
    Returns (validated_metadata, errors).
    """
    errors = []
    
    try:
        validated = AppraisalMetadata(**metadata_dict)
        return validated.model_dump(exclude_none=True), errors
    except Exception as e:
        errors.append(f"Metadata validation error: {str(e)}")
        # Return sanitized version with only known fields
        sanitized = {}
        known_fields = ['year', 'make', 'model', 'trim', 'mileage', 'color', 'vin']
        for field in known_fields:
            if field in metadata_dict:
                sanitized[field] = metadata_dict[field]
        return sanitized, errors
