from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.llm_client import get_llm_client
from app.validation import validate_vin_checksum
from app.vision_schemas import VisionExtractionEnvelope


PROMPT_VISION = """You are a vision assistant for auto appraisals.
Analyze the photo and extract vehicle information.

For photo angle classification, use one of: "front", "rear", "left", "right", "interior", "odometer", "vin", "damage", or "unknown"

- "front": Front view of the vehicle (showing front bumper, grille, headlights)
- "rear": Rear view of the vehicle (showing rear bumper, taillights, trunk)
- "left": Left side view of the vehicle (driver's side)
- "right": Right side view of the vehicle (passenger's side)
- "interior": Interior view (dashboard, seats, interior features)
- "odometer": Close-up photo of the odometer/dashboard showing mileage
- "vin": Close-up photo of the VIN plate/sticker (usually on dashboard or door jamb)
- "damage": Close-up photo specifically showing damage to the vehicle
- "unknown": If the angle cannot be determined

IMPORTANT: Return ONLY valid JSON matching this EXACT structure:
{
  "photo_id": "the-photo-id-provided",
  "extraction": {
    "photo_angle": {
      "angle": "front|rear|left|right|interior|odometer|vin|damage|unknown",
      "confidence": 0.0-1.0
    },
    "odometer": {
      "value": null or number,
      "unit": null or "miles|km",
      "confidence": 0.0-1.0
    },
    "vin": {
      "text": null or "VIN string",
      "confidence": 0.0-1.0
    },
    "damage": [
      {"description": "damage description", "severity": "minor|moderate|severe", "confidence": 0.0-1.0}
    ]
  }
}

If you don't find odometer/VIN/damage, set those fields to null or empty array. If uncertain, set confidence < 0.7."""

PROMPT_REPAIR = """The previous response had validation errors: {errors}

Please fix the JSON to match this EXACT structure:
{{
  "photo_id": "string",
  "extraction": {{
    "photo_angle": {{"angle": "front|rear|left|right|interior|odometer|vin|damage|unknown", "confidence": 0.0-1.0}},
    "odometer": {{"value": null or number, "unit": null or "miles|km", "confidence": 0.0-1.0}},
    "vin": {{"text": null or "VIN string", "confidence": 0.0-1.0}},
    "damage": [list of {{"description": "string", "severity": "string", "confidence": 0.0-1.0}}]
  }}
}}

Return only valid JSON matching this structure."""


def check_odometer_plausibility(value: float | None, confidence: float) -> tuple[float, str | None]:
    """Apply plausibility checks to odometer reading. Returns (adjusted_confidence, warning_message)."""
    if value is None:
        return confidence, None
    
    # Typical vehicle odometer range: 0 to 500,000 miles/km
    if value < 0 or value > 500_000:
        return 0.0, f"Odometer value {value} is outside plausible range (0-500,000)"
    
    # Flag suspiciously round numbers if confidence is high (possible misread)
    if value > 0 and value % 10000 == 0 and confidence > 0.8:
        return confidence * 0.7, f"Odometer value {value} is suspiciously round"
    
    return confidence, None


def check_vin_plausibility(text: str | None, confidence: float) -> tuple[float, str | None]:
    """Apply plausibility checks to VIN including checksum validation. Returns (adjusted_confidence, warning_message)."""
    if text is None:
        return confidence, None
    
    # VIN should be exactly 17 characters
    if len(text) != 17:
        return 0.0, f"VIN length {len(text)} is invalid (must be 17 characters)"
    
    # VIN should not contain I, O, or Q (to avoid confusion with 1, 0)
    if re.search(r'[IOQ]', text, re.IGNORECASE):
        return confidence * 0.5, "VIN contains invalid characters (I, O, or Q)"
    
    # VIN should be alphanumeric
    if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', text, re.IGNORECASE):
        return 0.0, "VIN contains invalid characters (must be A-Z, 0-9, excluding I, O, Q)"
    
    # Validate VIN checksum
    if not validate_vin_checksum(text):
        return 0.0, "VIN checksum validation failed (invalid VIN)"
    
    return confidence, None


def extract_from_photo(photo_url: str, photo_id: str) -> dict[str, Any]:
    """
    Call vision model on a single photo URL and validate against schema.
    Includes single retry with repair on validation failure.
    Applies plausibility checks to odometer and VIN.
    """
    client = get_llm_client()
    messages = [
        {
            "role": "system",
            "content": PROMPT_VISION,
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this appraisal photo."},
                {"type": "image_url", "image_url": {"url": photo_url}},
            ],
        },
    ]

    envelope = None
    validation_errors = None
    content = None
    
    for attempt in range(2):  # Initial + 1 retry
        try:
            raw = client.vision_completion(messages)
            choice = raw["choices"][0]
            content = choice["message"]["content"]
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content

            envelope = VisionExtractionEnvelope.model_validate(data)
            # Ensure the photo_id is set as expected
            if envelope.photo_id != photo_id:
                envelope.photo_id = photo_id
            
            # Apply plausibility checks
            warnings = []
            
            # Check odometer
            odo = envelope.extraction.odometer
            new_conf, warning = check_odometer_plausibility(odo.value, odo.confidence)
            if warning:
                warnings.append(warning)
            odo.confidence = new_conf
            
            # Check VIN
            vin = envelope.extraction.vin
            new_conf, warning = check_vin_plausibility(vin.text, vin.confidence)
            if warning:
                warnings.append(warning)
            vin.confidence = new_conf
            
            result = envelope.model_dump()
            if warnings:
                result["plausibility_warnings"] = warnings
            
            return result
            
        except (ValidationError, json.JSONDecodeError) as e:
            validation_errors = str(e)
            if attempt == 0 and content:
                # Retry with repair prompt
                messages.append({
                    "role": "assistant",
                    "content": content if isinstance(content, str) else json.dumps(content),
                })
                messages.append({
                    "role": "user",
                    "content": PROMPT_REPAIR.format(errors=validation_errors),
                })
            else:
                # Second attempt failed, return degraded output
                break
    
    # If both attempts failed, return minimal valid structure with low confidence
    return {
        "photo_id": photo_id,
        "extraction": {
            "photo_angle": {"angle": "unknown", "confidence": 0.0},
            "odometer": {"value": None, "unit": None, "confidence": 0.0},
            "vin": {"text": None, "confidence": 0.0},
            "damage": [],
        },
        "validation_error": validation_errors,
    }
