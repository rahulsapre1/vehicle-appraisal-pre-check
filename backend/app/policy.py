"""
Policy engine for decision readiness and action routing.

Rules:
1. Escalation: high-severity + high-confidence risk flags
2. Ready: score >= 75 AND no high-risk flags
3. Needs Evidence: fallback (any other case)
"""
from __future__ import annotations

from typing import Any


def should_exclude_vin_odometer_code(code: str) -> bool:
    """
    Check if a risk flag code should be excluded from escalation.
    Uses pattern matching to catch LLM variations of VIN/odometer missing/extraction failures.
    """
    code_upper = str(code).upper().strip()
    
    # Exact matches
    excluded_exact = {
        "VIN_EXTRACTION_FAIL",
        "ODOMETER_EXTRACTION_FAIL",
        "MISSING_VIN",
        "MISSING_ODOMETER",
        "MISSING_DATA",
        "MISSING_VIN_DATA",
        "MISSING_ODOMETER_DATA",
    }
    
    if code_upper in excluded_exact:
        return True
    
    # Pattern matching
    if (
        ("VIN" in code_upper and ("MISSING" in code_upper or "DATA" in code_upper or "EXTRACTION" in code_upper or "FAIL" in code_upper)) or
        ("ODOMETER" in code_upper and ("MISSING" in code_upper or "DATA" in code_upper or "EXTRACTION" in code_upper or "FAIL" in code_upper))
    ):
        return True
    
    return False


def check_escalation_rule(risk_flags: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """
    Check if any high-severity, high-confidence risk flags exist.
    Returns (should_escalate, reasons).
    
    Note: VIN/ODOMETER extraction failures and missing VIN/ODOMETER are excluded from escalation.
    """
    escalation_reasons = []
    
    for flag in risk_flags:
        # Handle both dict and object formats
        if isinstance(flag, dict):
            severity = flag.get("severity", "low")
            code = flag.get("code", "unknown")
            message = flag.get("message", "")
        elif hasattr(flag, "model_dump"):
            flag_dict = flag.model_dump()
            severity = flag_dict.get("severity", "low")
            code = flag_dict.get("code", "unknown")
            message = flag_dict.get("message", "")
        else:
            severity = getattr(flag, "severity", "low")
            code = getattr(flag, "code", "unknown")
            message = getattr(flag, "message", "")
        
        if severity == "high" and not should_exclude_vin_odometer_code(code):
            escalation_reasons.append(f"High-severity risk: {code} - {message}")
    
    return len(escalation_reasons) > 0, escalation_reasons


def check_ready_rule(total_score: int, risk_flags: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """
    Check if appraisal is ready for processing.
    Rules: score >= 75 AND no high-risk flags (excluding VIN/ODOMETER extraction failures).
    Returns (is_ready, reasons).
    """
    reasons = []
    
    # Check score threshold
    if total_score < 75:
        reasons.append(f"Score {total_score} is below threshold (75)")
        return False, reasons
    
    # Check for high-risk flags (excluding VIN/ODOMETER extraction failures)
    high_risk_flags = []
    for flag in risk_flags:
        if isinstance(flag, dict):
            severity = flag.get("severity", "low")
            code = flag.get("code", "unknown")
        elif hasattr(flag, "model_dump"):
            flag_dict = flag.model_dump()
            severity = flag_dict.get("severity", "low")
            code = flag_dict.get("code", "unknown")
        else:
            severity = getattr(flag, "severity", "low")
            code = getattr(flag, "code", "unknown")
        
        if severity == "high" and not should_exclude_vin_odometer_code(code):
            high_risk_flags.append(flag)
    
    high_risk_count = len(high_risk_flags)
    if high_risk_count > 0:
        reasons.append(f"Found {high_risk_count} high-risk flag(s)")
        return False, reasons
    
    # Check for medium-risk flags (warning but not blocking)
    medium_risk_count = sum(1 for flag in risk_flags if (flag.get("severity") if isinstance(flag, dict) else getattr(flag, "severity", "low")) == "medium")
    if medium_risk_count > 0:
        reasons.append(f"Warning: {medium_risk_count} medium-risk flag(s) present")
    
    reasons.append(f"Score {total_score} meets threshold, no high-risk flags")
    return True, reasons


def check_needs_evidence_rule(scoring_breakdown: dict[str, Any]) -> list[str]:
    """Identify what evidence is missing or insufficient. Returns list of missing evidence items."""
    missing = []
    
    breakdown = scoring_breakdown.get("breakdown", {})
    
    # Check angle coverage
    angle = breakdown.get("angle_coverage", {})
    if angle.get("score", 0) < 42:  # Less than 75% of max (56)
        missing_angles = angle.get("missing_angles", [])
        if missing_angles:
            missing.append(f"Missing photo angles: {', '.join(missing_angles)}")
        else:
            missing.append("Insufficient photo coverage")
    
    # Check odometer
    odometer = breakdown.get("odometer_confidence", {})
    if odometer.get("confidence", 0.0) < 0.7:
        missing.append("Odometer reading unclear or missing")
    
    # Check VIN
    vin = breakdown.get("vin_presence", {})
    if not vin.get("vin_present", False) or vin.get("confidence", 0.0) < 0.7:
        missing.append("VIN unclear or missing")
    
    # Check notes
    notes = breakdown.get("notes_consistency", {})
    if notes.get("score", 0) < 10:  # Less than 50% of max (20)
        missing.append("Notes missing or insufficient detail")
    
    return missing


def determine_decision_status(total_score: int, risk_flags: list[dict[str, Any]], scoring_breakdown: dict[str, Any]) -> dict[str, Any]:
    """
    Apply policy rules to determine final decision status.
    
    Priority:
    1. Escalation (if high-severity risks)
    2. Ready (if score >= 75 and no high risks)
    3. Needs Evidence (fallback)
    """
    # Filter out risk flags that should not trigger escalation
    filtered_risk_flags = []
    for flag in risk_flags:
        if isinstance(flag, dict):
            code = flag.get("code", "unknown")
        elif hasattr(flag, "model_dump"):
            flag_dict = flag.model_dump()
            code = flag_dict.get("code", "unknown")
        else:
            code = getattr(flag, "code", "unknown")
        
        if should_exclude_vin_odometer_code(code):
            continue
        
        filtered_risk_flags.append(flag)
    
    # Rule 1: Check escalation (using filtered flags)
    should_escalate, escalation_reasons = check_escalation_rule(filtered_risk_flags)
    if should_escalate:
        return {
            "status": "escalate",
            "reasons": escalation_reasons,
            "score": total_score,
        }
    
    # Rule 2: Check ready (using filtered flags)
    is_ready, ready_reasons = check_ready_rule(total_score, filtered_risk_flags)
    if is_ready:
        return {
            "status": "ready",
            "reasons": ready_reasons,
            "score": total_score,
        }
    
    # Rule 3: Needs evidence (fallback)
    missing_evidence = check_needs_evidence_rule(scoring_breakdown)
    return {
        "status": "needs_more_evidence",
        "reasons": missing_evidence,
        "score": total_score,
    }


def route_action(decision_status: str) -> dict[str, Any]:
    """Map decision status to next action."""
    action_map = {
        "ready": {
            "action": "route_to_adjuster_queue",
            "message": "Appraisal is ready for final decision processing"
        },
        "escalate": {
            "action": "route_to_senior_reviewer",
            "message": "Appraisal requires senior review due to high-risk flags"
        },
        "needs_more_evidence": {
            "action": "request_additional_evidence",
            "message": "Appraisal needs additional evidence before processing"
        },
    }
    return action_map.get(decision_status, {
        "action": "request_additional_evidence",
        "message": "Appraisal status unclear"
    })
