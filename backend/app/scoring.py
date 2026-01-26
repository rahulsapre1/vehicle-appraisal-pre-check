"""
Scoring functions for decision readiness.
Total possible: 100 points
- Angle coverage: 48 points (6 required angles: front, rear, left, right, interior, odometer)
- Odometer confidence: 15 points
- VIN presence: 10 points (optional - scored if present)
- Notes consistency: 20 points
- Damage confidence: 7 points (deprecated, now 0)
"""
from __future__ import annotations

from typing import Any


REQUIRED_ANGLES = ["front", "rear", "left", "right", "interior", "odometer"]

# Points per angle type
ANGLE_POINTS = {
    "front": 8,
    "rear": 8,
    "left": 8,
    "right": 8,
    "interior": 8,
    "odometer": 8,
}


def score_angle_coverage(vision_outputs: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Score based on required angle coverage.
    48 points max: 8 points per required angle (6 angles: front, rear, left, right, interior, odometer).
    """
    max_score = sum(ANGLE_POINTS.values())
    
    if len(vision_outputs) == 0:
        return {
            "score": 0,
            "max_score": max_score,
            "covered_angles": [],
            "missing_angles": REQUIRED_ANGLES.copy(),
            "reason": "No photos provided",
        }
    
    # Extract actual angles from vision outputs
    covered_angles_set = set()
    angle_confidence_map = {}
    
    for output in vision_outputs:
        extraction = output.get("extraction", {})
        photo_angle = extraction.get("photo_angle", {})
        angle = photo_angle.get("angle", "unknown")
        confidence = photo_angle.get("confidence", 0.0)
        
        # Only count angles with reasonable confidence (>= 0.7) and not "unknown"
        if angle != "unknown" and confidence >= 0.7:
            angle_lower = angle.lower()
            if angle_lower in REQUIRED_ANGLES:
                covered_angles_set.add(angle_lower)
                # Track highest confidence for each angle
                if angle_lower not in angle_confidence_map or confidence > angle_confidence_map[angle_lower]:
                    angle_confidence_map[angle_lower] = confidence
    
    # Calculate score based on covered angles
    covered_angles_list = sorted(list(covered_angles_set))
    missing_angles = [angle for angle in REQUIRED_ANGLES if angle not in covered_angles_set]
    
    # Award points for each covered angle (proportional to confidence)
    score = 0
    for angle in covered_angles_list:
        confidence = angle_confidence_map.get(angle, 0.5)
        max_points = ANGLE_POINTS.get(angle, 8)
        score += int(max_points * confidence)
    
    return {
        "score": score,
        "max_score": max_score,
        "covered_angles": covered_angles_list,
        "missing_angles": missing_angles,
        "angle_details": {angle: {"confidence": angle_confidence_map.get(angle, 0.0)} for angle in covered_angles_list},
        "reason": f"Covered {len(covered_angles_list)}/{len(REQUIRED_ANGLES)} required angles: {', '.join(covered_angles_list) if covered_angles_list else 'none'}",
    }


def score_odometer_confidence(vision_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Score based on odometer reading confidence with consistency checks. 15 points max."""
    max_score = 15
    
    if not vision_outputs:
        return {"score": 0, "max_score": max_score, "reason": "No vision outputs"}
    
    # Collect all odometer readings with confidence
    odometer_readings = []
    for output in vision_outputs:
        extraction = output.get("extraction", {})
        odometer = extraction.get("odometer", {})
        value = odometer.get("value")
        unit = odometer.get("unit")
        conf = odometer.get("confidence", 0.0)
        
        if value is not None and conf > 0:
            odometer_readings.append({
                "value": value,
                "unit": unit,
                "confidence": conf,
                "photo_id": output.get("photo_id", "unknown")
            })
    
    if not odometer_readings:
        return {"score": 0, "max_score": max_score, "reason": "No odometer readings found"}
    
    # Check unit consistency
    units = [r["unit"] for r in odometer_readings if r["unit"]]
    unique_units = set(units)
    unit_consistent = len(unique_units) <= 1
    
    # Check value consistency
    values = [r["value"] for r in odometer_readings]
    if len(values) > 1:
        value_range = max(values) - min(values)
        value_consistent = value_range <= 100
    else:
        value_consistent = True
    
    # Find highest confidence reading
    best_reading = max(odometer_readings, key=lambda x: x["confidence"])
    max_confidence = best_reading["confidence"]
    odometer_value = best_reading["value"]
    
    # Penalize if inconsistent
    consistency_penalty = 0.0
    warnings = []
    if not unit_consistent:
        consistency_penalty = 0.3
        warnings.append("Odometer units inconsistent across photos")
    if not value_consistent:
        consistency_penalty = max(consistency_penalty, 0.5)
        warnings.append(f"Odometer values inconsistent (range: {max(values) - min(values):.0f})")
    
    adjusted_confidence = max_confidence * (1 - consistency_penalty)
    score = int(max_score * adjusted_confidence)
    
    result = {
        "score": score,
        "max_score": max_score,
        "confidence": adjusted_confidence,
        "odometer_value": odometer_value,
        "reason": f"Odometer confidence: {adjusted_confidence:.2f}",
    }
    
    if warnings:
        result["warnings"] = warnings
        result["consistency_issues"] = True
    
    return result


def score_vin_presence(vision_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Score based on VIN presence and confidence with consistency checks. 10 points max."""
    max_score = 10
    
    if not vision_outputs:
        return {"score": 0, "max_score": max_score, "reason": "No vision outputs"}
    
    # Collect all VIN readings with confidence
    vin_readings = []
    for output in vision_outputs:
        extraction = output.get("extraction", {})
        vin = extraction.get("vin", {})
        text = vin.get("text")
        conf = vin.get("confidence", 0.0)
        
        if text and conf > 0:
            vin_readings.append({
                "text": text.upper().strip(),
                "confidence": conf,
                "photo_id": output.get("photo_id", "unknown")
            })
    
    if not vin_readings:
        return {
            "score": 0,
            "max_score": max_score,
            "confidence": 0.0,
            "vin_present": False,
            "reason": "No VIN readings found",
        }
    
    # Check VIN consistency across photos
    unique_vins = set(r["text"] for r in vin_readings)
    vin_consistent = len(unique_vins) == 1
    
    # Find highest confidence reading
    best_reading = max(vin_readings, key=lambda x: x["confidence"])
    max_confidence = best_reading["confidence"]
    vin_text = best_reading["text"]
    
    # Penalize if inconsistent
    consistency_penalty = 0.0
    warnings = []
    if not vin_consistent:
        consistency_penalty = 0.8  # Heavy penalty for different VINs
        warnings.append(f"Multiple different VINs detected: {', '.join(unique_vins)}")
    
    adjusted_confidence = max_confidence * (1 - consistency_penalty)
    score = int(max_score * adjusted_confidence)
    
    result = {
        "score": score,
        "max_score": max_score,
        "confidence": adjusted_confidence,
        "vin_present": True,
        "vin_text": vin_text,
        "reason": f"VIN confidence: {adjusted_confidence:.2f}",
    }
    
    if warnings:
        result["warnings"] = warnings
        result["consistency_issues"] = True
    
    return result


def score_damage_confidence(vision_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """DEPRECATED: Damage scoring removed - points redistributed to angle coverage. Returns 0 points always."""
    return {
        "score": 0,
        "max_score": 0,
        "reason": "Damage scoring removed (points redistributed to angle coverage)",
    }


def score_notes_consistency(notes: str, vision_outputs: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    """Score based on notes presence and consistency with vision. 20 points max."""
    max_score = 20
    
    if not notes or len(notes.strip()) < 10:
        return {
            "score": 0,
            "max_score": max_score,
            "reason": "Notes missing or too short",
        }
    
    # Award points proportionally to note length (simple heuristic)
    note_length = len(notes.strip())
    if note_length < 50:
        score = 5
        reason = "Notes present but minimal"
    elif note_length < 150:
        score = 12
        reason = "Notes present with moderate detail"
    else:
        score = max_score
        reason = "Notes present with good detail"
    
    return {
        "score": score,
        "max_score": max_score,
        "note_length": note_length,
        "reason": reason,
    }


def calculate_total_score(context: dict[str, Any]) -> dict[str, Any]:
    """Calculate total decision readiness score from all components."""
    vision_outputs = context.get("vision_outputs", [])
    notes = context.get("notes", "")
    metadata = context.get("normalized_metadata", {})
    
    angle_score = score_angle_coverage(vision_outputs, metadata)
    odometer_score = score_odometer_confidence(vision_outputs)
    vin_score = score_vin_presence(vision_outputs)
    damage_score = score_damage_confidence(vision_outputs)
    notes_score = score_notes_consistency(notes, vision_outputs, metadata)
    
    total = (
        angle_score["score"] +
        odometer_score["score"] +
        vin_score["score"] +
        damage_score["score"] +
        notes_score["score"]
    )
    
    max_total = 100
    
    return {
        "total_score": total,
        "max_score": max_total,
        "breakdown": {
            "angle_coverage": angle_score,
            "odometer_confidence": odometer_score,
            "vin_presence": vin_score,
            "damage_confidence": damage_score,
            "notes_consistency": notes_score,
        },
    }
