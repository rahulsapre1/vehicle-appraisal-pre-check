from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.llm_client import get_llm_client
from app.risk_schemas import EvidenceRef, RiskFlag, RiskScan


PROMPT_RISK = """You are a risk and consistency checker for auto appraisals.

SAFETY CONSTRAINTS (CRITICAL):
1. You MUST NOT suggest prices, valuations, or monetary amounts
2. You MUST NOT accuse anyone of fraud or criminal activity
3. You MUST only flag inconsistencies or missing evidence
4. You MUST provide evidence references for every flag
5. You MUST surface uncertainty - if confidence is low, say so explicitly

Your job is to identify:
- Inconsistencies between photos, notes, and metadata
- Missing or unclear evidence
- Suspicious patterns that warrant human review
- Low-confidence extractions that need verification

USING SIMILAR APPRAISALS (RAG):
If the context includes "similar_appraisals", these are historically similar cases retrieved via semantic search.
Use them to:
- Compare risk patterns (e.g., "Similar 2020 Camrys often had undisclosed flood damage")
- Validate expectations (e.g., "Typical mileage for this vehicle age is X based on similar cases")
- Identify anomalies (e.g., "This damage pattern is unusual compared to N similar appraisals")
- Learn from past flags (e.g., "Similar cases were escalated due to Y")

Always reference specific evidence (photo IDs, note sections, metadata fields).
When using similar appraisals, cite them as "based on similar historical cases".

Return your analysis as JSON with the following structure:
{
  "flags": [
    {
      "code": "EXAMPLE_CODE",
      "severity": "low|medium|high",
      "message": "Description of the issue",
      "evidence": [
        {"type": "photo", "id": "photo_id_here", "description": "What was observed"},
        {"type": "metadata", "id": "field_name", "description": "The metadata field"},
        {"type": "note", "id": null, "description": "Reference to notes section"}
      ]
    }
  ],
  "assumptions": ["List of assumptions made"],
  "unknowns": ["List of unknown factors"]
}

CRITICAL: Each evidence object MUST have a "type" field (one of: "photo", "metadata", "note", "vision", "similar_appraisal").
The "id" field is optional (can be null). The "description" field should explain what evidence supports the flag."""


def validate_safety_constraints(scan: RiskScan) -> list[str]:
    """Enforce safety constraints: no pricing, no fraud accusations. Returns list of violations."""
    violations = []
    forbidden_terms = [
        "price", "pricing", "value", "valuation", "worth", "$", "dollar",
        "fraud", "fraudulent", "scam", "fake", "forged", "criminal", "illegal"
    ]
    
    for flag in scan.flags:
        msg_lower = flag.message.lower()
        for term in forbidden_terms:
            if term in msg_lower:
                violations.append(f"Flag '{flag.code}' contains forbidden term '{term}'")
                break
    
    return violations


def check_metadata_consistency(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Check consistency between metadata and extracted vision data. Returns list of consistency flags."""
    flags = []
    metadata = context.get("normalized_metadata", {})
    vision_outputs = context.get("vision_outputs", [])
    
    # Check odometer consistency
    metadata_mileage = metadata.get("mileage")
    if metadata_mileage is not None:
        best_odometer = None
        best_confidence = 0.0
        for output in vision_outputs:
            extraction = output.get("extraction", {})
            odometer = extraction.get("odometer", {})
            value = odometer.get("value")
            conf = odometer.get("confidence", 0.0)
            if value is not None and conf > best_confidence:
                best_confidence = conf
                best_odometer = value
        
        if best_odometer is not None:
            difference = abs(metadata_mileage - best_odometer)
            if difference > 100:
                flags.append({
                    "code": "METADATA_ODOMETER_MISMATCH",
                    "severity": "medium",
                    "message": f"Metadata mileage ({metadata_mileage}) differs significantly from photo reading ({best_odometer})",
                    "evidence": ["metadata.mileage", "vision_outputs"]
                })
    
    # Check VIN consistency
    metadata_vin = metadata.get("vin")
    if metadata_vin:
        metadata_vin = metadata_vin.upper().strip()
        best_vin = None
        best_confidence = 0.0
        for output in vision_outputs:
            extraction = output.get("extraction", {})
            vin = extraction.get("vin", {})
            text = vin.get("text")
            conf = vin.get("confidence", 0.0)
            if text and conf > best_confidence:
                best_confidence = conf
                best_vin = text.upper().strip()
        
        if best_vin and metadata_vin != best_vin:
            flags.append({
                "code": "METADATA_VIN_MISMATCH",
                "severity": "high",
                "message": f"Metadata VIN ({metadata_vin}) does not match photo VIN ({best_vin})",
                "evidence": ["metadata.vin", "vision_outputs"]
            })
    
    return flags


def run_risk_scan(context: dict[str, Any]) -> dict[str, Any]:
    """
    Run text model over aggregated context (vision outputs, notes, metadata).
    Enforces safety constraints and ensures uncertainty is surfaced.
    Also performs deterministic metadata consistency checks.
    """
    # First, do deterministic metadata consistency checks
    metadata_flags = check_metadata_consistency(context)
    
    client = get_llm_client()
    messages = [
        {"role": "system", "content": PROMPT_RISK},
        {"role": "user", "content": json.dumps(context, indent=2)},
    ]

    try:
        raw = client.text_completion(messages, json_mode=True)
        choice = raw["choices"][0]
        content = choice["message"]["content"]
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content

        scan = RiskScan.model_validate(data)
        
        # Add metadata consistency flags
        for flag in metadata_flags:
            evidence_refs = [
                EvidenceRef(type=ev if isinstance(ev, str) else ev.get("type", "unknown"),
                           id=None, description=ev if isinstance(ev, str) else ev.get("description"))
                for ev in flag.get("evidence", [])
            ]
            risk_flag = RiskFlag(
                code=flag["code"],
                severity=flag["severity"],
                message=flag["message"],
                evidence=evidence_refs
            )
            scan.flags.append(risk_flag)
        
        # Validate safety constraints
        violations = validate_safety_constraints(scan)
        if violations:
            # Filter out violating flags
            scan.flags = [
                flag for flag in scan.flags
                if not any(term in flag.message.lower() 
                          for term in ["price", "pricing", "value", "valuation", "worth", "$", "dollar",
                                      "fraud", "fraudulent", "scam", "fake", "forged", "criminal", "illegal"])
            ]
            result = scan.model_dump()
            result["safety_violations"] = violations
            return result
        
        # Check that each flag has evidence references
        flags_without_evidence = [
            flag.code for flag in scan.flags if not (hasattr(flag, 'evidence') and flag.evidence)
        ]
        if flags_without_evidence:
            result = scan.model_dump()
            result["missing_evidence_refs"] = flags_without_evidence
            return result
        
        return scan.model_dump()
        
    except (ValidationError, json.JSONDecodeError) as e:
        # If parsing fails, return metadata flags if any
        if metadata_flags:
            return {
                "flags": metadata_flags,
                "error": str(e),
                "assumptions": [],
                "unknowns": [],
            }
        return {
            "flags": [],
            "error": str(e),
            "assumptions": [],
            "unknowns": [],
        }
    except Exception as e:
        # Catch all other errors (like API errors)
        return {
            "flags": metadata_flags if metadata_flags else [],
            "error": f"Text model error: {str(e)}",
            "assumptions": [],
            "unknowns": [],
        }
