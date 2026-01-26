"""LangChain tools for appraisal processing"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

try:
    from langchain_core.tools import tool
except ImportError:
    # Fallback if langchain not available
    def tool(func):
        """Dummy decorator if langchain not available"""
        return func

# These will be imported when backend modules are created
# from app.vision import extract_from_photo
# from app.risk import run_risk_scan
# from app.scoring import calculate_total_score
# from app.policy import determine_decision_status, route_action

# Shared context for agent execution
_agent_context: dict[str, Any] = {
    "vision_outputs": [],
    "metadata": {},
    "notes": "",
}


def set_agent_context(metadata: dict[str, Any], notes: str) -> None:
    """Initialize agent context for a new run."""
    global _agent_context
    _agent_context = {
        "vision_outputs": [],
        "metadata": metadata,
        "notes": notes,
    }


def get_agent_context() -> dict[str, Any]:
    """Get current agent context."""
    return _agent_context


@tool
def extract_vision_from_photo(photo_url: str, photo_id: str) -> dict[str, Any]:
    """
    Extract vehicle information from a photo using vision model.
    Uses cached vision data if available, otherwise calls vision API.
    Automatically stores results in agent context for later analysis.
    
    Args:
        photo_url: Signed URL or path to the photo
        photo_id: Unique identifier for the photo (artifact ID)
        
    Returns:
        Dictionary with extraction results including:
        - photo_angle: Detected angle and confidence
        - odometer: Odometer reading if found
        - vin: VIN if found
        - damage: List of damage items detected
    """
    try:
        from app.vision import extract_from_photo
        
        # Check for cached vision data
        cached_result = _try_get_cached_vision_data(photo_id)
        if cached_result and not cached_result.get("error"):
            _agent_context["vision_outputs"].append(cached_result)
            return cached_result
        
        # Extract fresh
        result = extract_from_photo(photo_url, photo_id)
        _agent_context["vision_outputs"].append(result)
        return result
    except Exception as e:
        error_result = {
            "photo_id": photo_id,
            "error": str(e),
            "extraction": {
                "photo_angle": {"angle": "unknown", "confidence": 0.0},
                "odometer": {"value": None, "unit": None, "confidence": 0.0},
                "vin": {"text": None, "confidence": 0.0},
                "damage": [],
            }
        }
        _agent_context["vision_outputs"].append(error_result)
        return error_result


def _try_get_cached_vision_data(artifact_id: str) -> dict[str, Any] | None:
    """Try to retrieve cached vision data from the artifact's vision_output_json field."""
    try:
        from app.supabase_client import get_supabase_client
        
        supabase = get_supabase_client()
        result = supabase.table("artifacts").select("vision_output_json").eq("id", artifact_id).single().execute()
        
        if result.data and result.data.get("vision_output_json"):
            vision_data = result.data["vision_output_json"]
            if vision_data.get("extraction") and not vision_data.get("validation_error"):
                return vision_data
        
        return None
    except Exception:
        return None


@tool
def check_evidence_completeness() -> dict[str, Any]:
    """
    Check what evidence is missing for the appraisal based on photos analyzed so far.
    Uses vision outputs collected from previous extract_vision_from_photo calls.
    
    Returns:
        Dictionary with:
        - missing_angles: List of required angles not found
        - covered_angles: List of angles that were found
        - photo_count: Number of photos analyzed
        - completeness_score: Score from 0-100
        - odometer_status: Status of odometer evidence
        - vin_status: Status of VIN evidence
    """
    try:
        from app.scoring import score_angle_coverage
        
        vision_outputs = _agent_context.get("vision_outputs", [])
        metadata = _agent_context.get("metadata", {})
        
        # Calculate angle coverage
        angle_result = score_angle_coverage(vision_outputs, metadata)
        
        # Check odometer and VIN from vision outputs
        odometer_found = False
        vin_found = False
        
        for output in vision_outputs:
            extraction = output.get("extraction", {})
            if extraction.get("odometer", {}).get("value"):
                odometer_found = True
            if extraction.get("vin", {}).get("text"):
                vin_found = True
        
        return {
            "missing_angles": angle_result.get("missing_angles", []),
            "covered_angles": angle_result.get("covered_angles", []),
            "photo_count": len(vision_outputs),
            "completeness_score": angle_result.get("score", 0),
            "odometer_status": "found" if odometer_found else "missing",
            "vin_status": "found" if vin_found else "missing",
            "is_complete": len(angle_result.get("missing_angles", [])) == 0,
            "photos_analyzed": len(vision_outputs),
        }
    except Exception as e:
        return {
            "missing_angles": [],
            "covered_angles": [],
            "photo_count": 0,
            "completeness_score": 0,
            "odometer_status": "unknown",
            "vin_status": "unknown",
            "error": str(e),
        }


@tool
def retrieve_similar_appraisals() -> dict[str, Any]:
    """
    Retrieve similar historical appraisals using RAG (Retrieval-Augmented Generation).
    Only works if ENABLE_RAG=true and historical embeddings exist.
    
    Returns similar appraisals with their outcomes to provide context for risk analysis.
    
    Returns:
        Dictionary with:
        - similar_count: Number of similar appraisals found
        - similar_cases: List of similar appraisals with outcomes
        - rag_enabled: Whether RAG is enabled
    """
    import os
    
    if not os.getenv("ENABLE_RAG", "false").lower() == "true":
        return {"similar_count": 0, "similar_cases": [], "rag_enabled": False}
    
    try:
        # Import RAG utilities
        current_file = Path(__file__).resolve()
        shared_path = current_file.parent.parent.parent
        rag_package_path = shared_path / "rag"
        
        if str(rag_package_path) not in sys.path:
            sys.path.insert(0, str(rag_package_path))
        
        from rag.retrieval import build_query_text_from_context, retrieve_similar_appraisals as rag_retrieve
        
        # Build query from current context
        context = {
            "ingest_normalize": {
                "normalized_metadata": _agent_context.get("metadata", {}),
                "notes": _agent_context.get("notes", ""),
            },
            "vision_per_image": {
                "vision_outputs": _agent_context.get("vision_outputs", [])
            }
        }
        
        query_text = build_query_text_from_context(context)
        
        if not query_text:
            return {"similar_count": 0, "similar_cases": [], "rag_enabled": True, "query_empty": True}
        
        # Retrieve similar appraisals
        similar_result = rag_retrieve(
            query_text=query_text,
            limit=5,
            match_threshold=0.7,
            content_types=None,
        )
        
        similar = similar_result.get("similar_appraisals", [])
        
        # Format for agent comprehension
        formatted_cases = []
        for idx, result in enumerate(similar[:3], 1):  # Top 3
            formatted_entry = {
                "rank": idx,
                "similarity_score": result.get("similarity", 0.0),
                "vehicle": result.get("metadata_json", {}),
                "matched_content": result.get("content_text", ""),
            }
            
            if result.get("historical_outcome"):
                formatted_entry["historical_outcome"] = result.get("historical_outcome")
            
            formatted_cases.append(formatted_entry)
        
        _agent_context["similar_appraisals"] = formatted_cases
        
        return {
            "similar_count": len(similar),
            "similar_cases": formatted_cases,
            "rag_enabled": True,
            "rag_error": similar_result.get("rag_error"),
        }
    except Exception as e:
        return {
            "similar_count": 0,
            "similar_cases": [],
            "rag_enabled": True,
            "error": str(e),
        }


@tool
def scan_for_risks() -> dict[str, Any]:
    """
    Scan for risks and inconsistencies in the appraisal based on data collected so far.
    Uses vision outputs, metadata, and notes from agent context.
    
    IMPORTANT: Call retrieve_similar_appraisals() BEFORE this tool to enable
    historical context-aware risk analysis.
            
    Returns:
        Dictionary with:
        - flags: List of risk flags with severity and messages
        - assumptions: List of assumptions made
        - unknowns: List of unknown factors
        - used_historical_context: Whether similar appraisals were used
    """
    try:
        from app.risk import run_risk_scan
        
        context = {
            "normalized_metadata": _agent_context.get("metadata", {}),
            "notes": _agent_context.get("notes", ""),
            "vision_outputs": _agent_context.get("vision_outputs", []),
        }
        
        # Add similar appraisals if available
        similar_cases = _agent_context.get("similar_appraisals", [])
        if similar_cases:
            context["similar_historical_appraisals"] = {
                "count": len(similar_cases),
                "description": "Similar appraisals from historical data retrieved via semantic search",
                "cases": similar_cases,
            }
        
        result = run_risk_scan(context)
        result["used_historical_context"] = len(similar_cases) > 0
        _agent_context["risk_and_consistency"] = result
        return result
    except Exception as e:
        error_result = {
            "flags": [],
            "error": str(e),
            "assumptions": [],
            "unknowns": [],
            "used_historical_context": False,
        }
        _agent_context["risk_and_consistency"] = error_result
        return error_result


@tool
def calculate_readiness_score() -> dict[str, Any]:
    """
    Calculate decision readiness score and determine status based on all data collected.
    Uses vision outputs, metadata, notes, and risk flags from agent context.
            
    Returns:
        Dictionary with:
        - score: Total readiness score (0-100)
        - status: Decision status (ready, escalate, needs_more_evidence)
        - reasons: List of reasons for the decision
        - score_breakdown: Detailed breakdown of scoring components
    """
    try:
        from app.scoring import calculate_total_score
        from app.policy import determine_decision_status, route_action
        
        scoring_result = calculate_total_score({
            "vision_outputs": _agent_context.get("vision_outputs", []),
            "notes": _agent_context.get("notes", ""),
            "normalized_metadata": _agent_context.get("metadata", {}),
        })
        
        total_score = scoring_result["total_score"]
        risk_flags = _agent_context.get("risk_and_consistency", {}).get("flags", [])
        
        # Apply policy rules
        decision = determine_decision_status(total_score, risk_flags, scoring_result)
        next_action = route_action(decision["status"])
        
        return {
            "score": total_score,
            "status": decision["status"],
            "reasons": decision["reasons"],
            "score_breakdown": scoring_result["breakdown"],
            "next_action": next_action,
        }
    except Exception as e:
        return {
            "score": 0,
            "status": "needs_more_evidence",
            "reasons": [f"Error calculating score: {str(e)}"],
            "score_breakdown": {},
            "error": str(e),
        }


def get_appraisal_tools() -> list:
    """Get list of all appraisal tools for the agent."""
    return [
        extract_vision_from_photo,
        check_evidence_completeness,
        retrieve_similar_appraisals,
        scan_for_risks,
        calculate_readiness_score,
    ]
