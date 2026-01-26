"""Agent executor with ledger integration"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add shared packages to path
current_file = Path(__file__).resolve()
shared_path = current_file.parent.parent.parent

# Add backend to path
backend_path = Path("/app")
if not (backend_path / "app").exists():
    for parent in current_file.parents:
        candidate = parent / "backend"
        if candidate.exists():
            backend_path = candidate
            break

if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from supabase import Client

try:
    from langchain.agents import AgentExecutor
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    class AgentExecutor:
        pass

from ledger.ledger.writer import append_ledger_event
from .tools import set_agent_context, get_agent_context


def execute_agent_with_ledger(
    agent: AgentExecutor,
    supabase: Client,
    appraisal_id: str,
    pipeline_run_id: str,
    initial_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute agent and log each step to ledger.
    
    Args:
        agent: AgentExecutor instance
        supabase: Supabase client
        appraisal_id: UUID of the appraisal
        pipeline_run_id: UUID of the pipeline run
        initial_context: Initial context dictionary
        
    Returns:
        Dictionary with final results matching sequential pipeline format
    """
    if not LANGCHAIN_AVAILABLE:
        raise ImportError("LangChain is required for agentic mode")
    
    # Initialize shared context for tools
    appraisal = initial_context.get("appraisal", {})
    metadata = appraisal.get("metadata_json", {})
    notes = appraisal.get("notes_raw", "")
    set_agent_context(metadata=metadata, notes=notes)
    
    # Log agent start
    append_ledger_event(
        supabase=supabase,
        appraisal_id=appraisal_id,
        pipeline_run_id=pipeline_run_id,
        node_name="agent_start",
        schema_version="v1",
        input_refs={"context_keys": list(initial_context.keys())},
        output={
            "mode": "agentic",
            "initial_context_keys": list(initial_context.keys()),
            "artifact_count": len(initial_context.get("artifacts", [])),
        },
        confidence_summary=None,
        status="ok",
    )
    
    # Build input for agent
    appraisal = initial_context.get("appraisal", {})
    metadata = appraisal.get("metadata_json", {})
    notes = appraisal.get("notes_raw", "")
    artifacts = initial_context.get("artifacts", [])
    
    # Build photo list with URLs and IDs for the agent
    photo_list = []
    for artifact in artifacts:
        if artifact.get("signed_url"):
            photo_list.append({
                "id": artifact.get("id"),
                "url": artifact.get("signed_url"),
            })
    
    # Format photo information for agent
    photos_text = "\n".join([
        f"- Photo ID: {photo['id']}, URL: {photo['url']}"
        for photo in photo_list
    ])
    
    agent_input = f"""Process appraisal {appraisal_id}.

Vehicle Information:
- Year: {metadata.get('year', 'N/A')}
- Make: {metadata.get('make', 'N/A')}
- Model: {metadata.get('model', 'N/A')}
- Mileage: {metadata.get('mileage', 'N/A')}
- Notes: {notes[:500] if notes else 'None'}

Available Photos ({len(photo_list)} total):
{photos_text if photos_text else "No photos available"}

Your task:
1. Extract information from ALL photos using extract_vision_from_photo tool
   - Call extract_vision_from_photo(photo_url=<url>, photo_id=<id>) for EACH photo above
   - Use the exact URLs and IDs provided
2. After extracting ALL photos, check evidence completeness
3. IMPORTANT: Call retrieve_similar_appraisals() to find similar historical cases
4. Scan for risks and inconsistencies (this will use historical context from step 3)
5. Calculate readiness score
6. Provide final recommendation

IMPORTANT: You MUST use the exact photo_url and photo_id values provided above. Do not make up placeholder URLs."""
    
    try:
        # Execute agent
        result = agent.invoke({
            "input": agent_input,
        })
        
        # Extract final output
        final_output = result.get("output", "")
        intermediate_steps = result.get("intermediate_steps", [])
        
        # Log each tool call as a ledger event
        for step_idx, (action, observation) in enumerate(intermediate_steps):
            tool_name = action.tool if hasattr(action, "tool") else "unknown_tool"
            tool_input = action.tool_input if hasattr(action, "tool_input") else {}
            
            append_ledger_event(
                supabase=supabase,
                appraisal_id=appraisal_id,
                pipeline_run_id=pipeline_run_id,
                node_name=f"agent_tool_{tool_name}",
                schema_version="v1",
                input_refs={"tool": tool_name, "step": step_idx, "input": tool_input},
                output={
                    "tool": tool_name,
                    "observation": str(observation)[:1000],  # Truncate long observations
                    "step": step_idx,
                },
                confidence_summary=None,
                status="ok",
            )
        
        # Log agent completion
        append_ledger_event(
            supabase=supabase,
            appraisal_id=appraisal_id,
            pipeline_run_id=pipeline_run_id,
            node_name="agent_complete",
            schema_version="v1",
            input_refs={},
            output={
                "final_output": final_output[:2000],  # Truncate if too long
                "steps_count": len(intermediate_steps),
                "mode": "agentic",
            },
            confidence_summary=None,
            status="ok",
        )
        
        # Get results from shared context (where tools stored them)
        context_results = get_agent_context()
        
        # Extract structured results
        vision_outputs = context_results.get("vision_outputs", [])
        risk_and_consistency = context_results.get("risk_and_consistency", {})
        
        # Build evidence completeness from vision outputs
        evidence_completeness = {}
        if vision_outputs:
            from app.scoring import score_angle_coverage
            metadata = context_results.get("metadata", {})
            angle_result = score_angle_coverage(vision_outputs, metadata)
            evidence_completeness = {
                "missing_angles": angle_result.get("missing_angles", []),
                "covered_angles": angle_result.get("covered_angles", []),
                "photo_count": len(vision_outputs),
                "is_complete": len(angle_result.get("missing_angles", [])) == 0,
            }
        
        # Build decision readiness
        decision_readiness = {}
        if vision_outputs:
            from app.scoring import calculate_total_score
            from app.policy import determine_decision_status, route_action
            
            scoring_result = calculate_total_score({
                "vision_outputs": vision_outputs,
                "notes": context_results.get("notes", ""),
                "normalized_metadata": context_results.get("metadata", {}),
            })
            
            total_score = scoring_result["total_score"]
            risk_flags = risk_and_consistency.get("flags", [])
            decision = determine_decision_status(total_score, risk_flags, scoring_result)
            next_action = route_action(decision["status"])
            
            decision_readiness = {
                "score": total_score,
                "status": decision["status"],
                "reasons": decision["reasons"],
                "breakdown": scoring_result["breakdown"],
                "next_action": next_action,
            }
        
        # Return structured result matching sequential pipeline format
        return {
            "agent_output": final_output,
            "intermediate_steps_count": len(intermediate_steps),
            "mode": "agentic",
            "execution_summary": {
                "tools_used": [step[0].tool if hasattr(step[0], "tool") else "unknown" 
                              for step in intermediate_steps],
            },
            # Include actual pipeline results
            "ingest_normalize": {
                "normalized_metadata": context_results.get("metadata", {}),
                "notes": context_results.get("notes", ""),
            },
            "vision_per_image": {
                "vision_outputs": vision_outputs,
            },
            "evidence_completeness": evidence_completeness,
            "risk_and_consistency": risk_and_consistency,
            "decision_readiness": decision_readiness,
            "action_router": decision_readiness.get("next_action", {}) if decision_readiness else {},
            "ledger_finalization": {
                "status": "completed",
                "mode": "agentic",
            },
        }
        
    except Exception as e:
        # Log agent error
        append_ledger_event(
            supabase=supabase,
            appraisal_id=appraisal_id,
            pipeline_run_id=pipeline_run_id,
            node_name="agent_error",
            schema_version="v1",
            input_refs={},
            output={"error": str(e)},
            confidence_summary=None,
            status="fail",
            error=str(e),
        )
        
        raise
