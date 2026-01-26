"""
Agentic pipeline orchestrator for appraisal processing.
Executes pipeline using LangChain agent with ledger integration.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add shared packages to path
current_file = Path(__file__).resolve()
shared_path = current_file.parent.parent.parent.parent / "shared"

if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from supabase import Client

from app.supabase_client import get_supabase_client

try:
    from agent.agent.agent import create_appraisal_agent
    from agent.agent.executor import execute_agent_with_ledger
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False


async def run_pipeline_agentic_async(pipeline_run_id: str, appraisal_id: str) -> str:
    """
    Execute pipeline using agentic mode (LangChain agent).
    Agent decides which tools to use and in what order.
    
    Args:
        pipeline_run_id: UUID of the pipeline run
        appraisal_id: UUID of the appraisal
        
    Returns:
        Result string with execution summary
    """
    if not AGENT_AVAILABLE:
        supabase = get_supabase_client()
        def update_failed_import():
            supabase.table("pipeline_runs").update({
                "status": "FAILED",
                "completed_at": datetime.utcnow().isoformat(),
                "outputs_json": {"error": "Agent framework not available. Install langchain and langchain-openai."}
            }).eq("id", pipeline_run_id).execute()
        
        await asyncio.to_thread(update_failed_import)
        raise ImportError("Agent framework not available")
    
    supabase = get_supabase_client()

    # Mark as running and set started_at
    def update_status():
        supabase.table("pipeline_runs").update({
            "status": "RUNNING",
            "started_at": datetime.utcnow().isoformat()
        }).eq("id", pipeline_run_id).execute()
    
    await asyncio.to_thread(update_status)

    try:
        # Fetch appraisal data
        def fetch_appraisal():
            return supabase.table("appraisals").select("*").eq("id", appraisal_id).single().execute()
        
        def fetch_artifacts():
            return supabase.table("artifacts").select("*").eq("appraisal_id", appraisal_id).execute()
        
        appraisal_data = await asyncio.to_thread(fetch_appraisal)
        artifacts_data = await asyncio.to_thread(fetch_artifacts)
        artifacts = artifacts_data.data or []
        
        # Create signed URLs for artifacts in parallel
        from app.storage import create_signed_url
        
        async def generate_signed_url_async(artifact):
            storage_path = artifact.get("storage_path")
            if storage_path:
                try:
                    def create_url():
                        return create_signed_url(supabase, storage_path, expires_in_seconds=3600)
                    return await asyncio.to_thread(create_url)
                except Exception:
                    return None
            return None
        
        if artifacts:
            signed_url_tasks = [generate_signed_url_async(artifact) for artifact in artifacts]
            signed_urls = await asyncio.gather(*signed_url_tasks, return_exceptions=True)
            
            for artifact, signed_url in zip(artifacts, signed_urls):
                if isinstance(signed_url, Exception) or signed_url is None:
                    artifact["signed_url"] = None
                else:
                    artifact["signed_url"] = signed_url
        
        # Create agent with settings from environment
        from app.settings import get_settings
        settings = get_settings()
        agent = create_appraisal_agent(
            max_iterations=settings.agent_max_iterations,
            max_execution_time=settings.agent_execution_timeout_seconds
        )
        
        # Build initial context
        initial_context = {
            "appraisal": appraisal_data.data,
            "artifacts": artifacts,
        }
        
        # Execute agent with ledger tracking
        def execute_agent():
            return execute_agent_with_ledger(
                agent=agent,
                supabase=supabase,
                appraisal_id=appraisal_id,
                pipeline_run_id=pipeline_run_id,
                initial_context=initial_context,
            )
        
        result = await asyncio.to_thread(execute_agent)
        
        final_status = "COMPLETED"
        
        # Update with final status and outputs
        def update_completed():
            supabase.table("pipeline_runs").update({
                "status": final_status,
                "outputs_json": result,
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", pipeline_run_id).execute()
        
        await asyncio.to_thread(update_completed)
        
    except Exception as e:
        # Mark as failed
        def update_failed():
            supabase.table("pipeline_runs").update({
                "status": "FAILED",
                "completed_at": datetime.utcnow().isoformat(),
                "outputs_json": {"error": str(e)}
            }).eq("id", pipeline_run_id).execute()
        
        await asyncio.to_thread(update_failed)
        raise

    # Update appraisals.latest_run_id
    def update_latest_run():
        supabase.table("appraisals").update({"latest_run_id": pipeline_run_id}).eq("id", appraisal_id).execute()
    
    await asyncio.to_thread(update_latest_run)

    # Async embedding generation (non-blocking, fire-and-forget)
    import os
    if os.getenv("ENABLE_RAG", "false").lower() == "true":
        try:
            # Trigger async embedding generation task
            asyncio.create_task(generate_embeddings_async(pipeline_run_id, appraisal_id, result))
        except Exception:
            # Don't fail pipeline if embedding generation fails
            pass

    return f"pipeline finished with status={final_status}, context_keys={list(result.keys())}"


async def generate_embeddings_async(pipeline_run_id: str, appraisal_id: str, context: dict[str, Any]) -> str:
    """
    Generate and store embeddings for an appraisal (async, non-blocking).
    This task runs after pipeline completion and doesn't block the main pipeline.
    """
    import os
    
    if not os.getenv("ENABLE_RAG", "false").lower() == "true":
        return "RAG disabled, skipping embedding generation"
    
    try:
        # Import RAG utilities
        current_file = Path(__file__).resolve()
        shared_path = current_file.parent.parent.parent.parent / "shared"
        rag_package_path = shared_path / "rag"
        
        if str(rag_package_path) not in sys.path:
            sys.path.insert(0, str(rag_package_path))
        
        from rag.rag.embeddings import generate_embedding_async
        from rag.rag.vector_store import store_embedding
        from rag.rag.retrieval import build_query_text_from_context
        
        supabase = get_supabase_client()
        
        # Build query text from context
        query_text = build_query_text_from_context(context)
        
        if not query_text:
            return "No query text generated, skipping embedding"
        
        # Generate embedding
        embedding = await generate_embedding_async(query_text)
        
        # Store embedding
        await asyncio.to_thread(
            store_embedding,
            supabase=supabase,
            appraisal_id=appraisal_id,
            content_type="metadata",
            content_text=query_text,
            embedding=embedding,
            pipeline_run_id=pipeline_run_id,
        )
        
        return f"Embedding generated and stored for appraisal {appraisal_id}"
        
    except Exception as e:
        # Don't raise - this is a background task
        return f"Embedding generation failed: {str(e)}"
