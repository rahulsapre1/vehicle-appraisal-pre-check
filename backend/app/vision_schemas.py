from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class PhotoAngle(str, Enum):
    """Valid photo angles for vehicle appraisals."""
    FRONT = "front"
    REAR = "rear"
    LEFT = "left"
    RIGHT = "right"
    INTERIOR = "interior"
    ODOMETER = "odometer"
    VIN = "vin"
    DAMAGE = "damage"
    UNKNOWN = "unknown"


class VisionPhotoAngle(BaseModel):
    """Photo angle classification."""
    angle: PhotoAngle = PhotoAngle.UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class VisionOdometer(BaseModel):
    value: float | None = None
    unit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class VisionVin(BaseModel):
    text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class VisionDamage(BaseModel):
    description: str | None = None
    severity: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class VisionExtraction(BaseModel):
    photo_angle: VisionPhotoAngle
    odometer: VisionOdometer
    vin: VisionVin
    damage: list[VisionDamage] = Field(default_factory=list)


class VisionExtractionEnvelope(BaseModel):
    """Top-level schema for vision model response."""
    photo_id: str
    extraction: VisionExtraction
