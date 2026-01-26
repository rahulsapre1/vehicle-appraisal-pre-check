"""Tools for interacting with the appraisal system via API"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

# Add parent directory to path for imports
current_file = Path(__file__).resolve()
parent_dir = current_file.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))


API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
# Increased timeout for production (slower free tier, cold starts)
API_TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "60.0"))  # 60s for production


async def get_appraisal_status(appraisal_id: str) -> dict[str, Any]:
    """
    Get the current status, readiness score, and decision for an appraisal.
    
    Args:
        appraisal_id: UUID or short_id (4 characters) of the appraisal
        
    Returns:
        Dictionary with appraisal status, readiness score, and decision
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/api/appraisals/{appraisal_id}")
            response.raise_for_status()
            data = response.json()
            
            # Extract key information
            appraisal = data.get("appraisal", {})
            latest_run = data.get("latest_run", {})
            outputs = latest_run.get("outputs_json", {}) if latest_run else {}
            decision_readiness = outputs.get("decision_readiness", {})
            
            return {
                "appraisal_id": appraisal.get("id"),
                "short_id": appraisal.get("short_id"),
                "status": latest_run.get("status", "unknown") if latest_run else "no_runs",
                "readiness_score": decision_readiness.get("score"),
                "readiness_status": decision_readiness.get("status"),
                "decision_reasons": decision_readiness.get("reasons", []),
                "created_at": appraisal.get("created_at"),
                "pipeline_run_id": latest_run.get("id") if latest_run else None,
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "message": e.response.text,
            }
        except Exception as e:
            return {
                "error": f"Failed to get appraisal status: {str(e)}",
            }


async def check_evidence_completeness(appraisal_id: str) -> dict[str, Any]:
    """
    Check what evidence is missing or incomplete for an appraisal.
    
    Args:
        appraisal_id: UUID or short_id (4 characters) of the appraisal
        
    Returns:
        Dictionary with missing evidence details and completeness score
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/api/appraisals/{appraisal_id}")
            response.raise_for_status()
            data = response.json()
            
            latest_run = data.get("latest_run", {})
            outputs = latest_run.get("outputs_json", {}) if latest_run else {}
            evidence_completeness = outputs.get("evidence_completeness", {})
            decision_readiness = outputs.get("decision_readiness", {})
            
            return {
                "appraisal_id": data.get("appraisal", {}).get("id"),
                "short_id": data.get("appraisal", {}).get("short_id"),
                "is_complete": evidence_completeness.get("is_complete", False),
                "photo_count": evidence_completeness.get("photo_count", 0),
                "missing_angles": evidence_completeness.get("missing_angles", []),
                "covered_angles": evidence_completeness.get("covered_angles", []),
                "missing_evidence": decision_readiness.get("reasons", []),
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "message": e.response.text,
            }
        except Exception as e:
            return {
                "error": f"Failed to check evidence completeness: {str(e)}",
            }


async def get_risk_flags(appraisal_id: str) -> dict[str, Any]:
    """
    Get all risk flags and consistency issues identified for an appraisal.
    
    Args:
        appraisal_id: UUID or short_id (4 characters) of the appraisal
        
    Returns:
        Dictionary with risk flags, severity, and evidence references
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/api/appraisals/{appraisal_id}")
            response.raise_for_status()
            data = response.json()
            
            latest_run = data.get("latest_run", {})
            outputs = latest_run.get("outputs_json", {}) if latest_run else {}
            risk_scan = outputs.get("risk_and_consistency", {})
            
            flags = risk_scan.get("flags", [])
            
            # Categorize flags by severity
            high_severity = [f for f in flags if f.get("severity") == "high"]
            medium_severity = [f for f in flags if f.get("severity") == "medium"]
            low_severity = [f for f in flags if f.get("severity") == "low"]
            
            return {
                "appraisal_id": data.get("appraisal", {}).get("id"),
                "short_id": data.get("appraisal", {}).get("short_id"),
                "total_flags": len(flags),
                "high_severity_count": len(high_severity),
                "medium_severity_count": len(medium_severity),
                "low_severity_count": len(low_severity),
                "high_severity_flags": high_severity,
                "medium_severity_flags": medium_severity,
                "low_severity_flags": low_severity,
                "all_flags": flags,
                "assumptions": risk_scan.get("assumptions", []),
                "unknowns": risk_scan.get("unknowns", []),
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "message": e.response.text,
            }
        except Exception as e:
            return {
                "error": f"Failed to get risk flags: {str(e)}",
            }


async def get_decision_readiness(appraisal_id: str) -> dict[str, Any]:
    """
    Get the decision readiness assessment including score breakdown and next actions.
    
    Args:
        appraisal_id: UUID or short_id (4 characters) of the appraisal
        
    Returns:
        Dictionary with readiness score, status, breakdown, and recommended actions
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/api/appraisals/{appraisal_id}")
            response.raise_for_status()
            data = response.json()
            
            latest_run = data.get("latest_run", {})
            outputs = latest_run.get("outputs_json", {}) if latest_run else {}
            decision_readiness = outputs.get("decision_readiness", {})
            
            return {
                "appraisal_id": data.get("appraisal", {}).get("id"),
                "short_id": data.get("appraisal", {}).get("short_id"),
                "readiness_score": decision_readiness.get("score"),
                "readiness_status": decision_readiness.get("status"),
                "score_breakdown": decision_readiness.get("breakdown", {}),
                "decision_reasons": decision_readiness.get("reasons", []),
                "next_action": decision_readiness.get("next_action", {}),
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "message": e.response.text,
            }
        except Exception as e:
            return {
                "error": f"Failed to get decision readiness: {str(e)}",
            }


async def get_ledger_events(appraisal_id: str) -> dict[str, Any]:
    """
    Get the complete audit ledger (event log) for an appraisal.
    
    Args:
        appraisal_id: UUID or short_id (4 characters) of the appraisal
        
    Returns:
        Dictionary with all ledger events in chronological order
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/api/appraisals/{appraisal_id}/ledger")
            response.raise_for_status()
            data = response.json()
            
            events = data.get("events", [])
            
            return {
                "appraisal_id": appraisal_id,
                "total_events": len(events),
                "events": events,
                "node_summary": {
                    event.get("node_name"): {
                        "status": event.get("status"),
                        "timestamp": event.get("timestamp"),
                    }
                    for event in events
                    if event.get("node_name")
                },
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code}",
                "message": e.response.text,
            }
        except Exception as e:
            return {
                "error": f"Failed to get ledger events: {str(e)}",
            }
