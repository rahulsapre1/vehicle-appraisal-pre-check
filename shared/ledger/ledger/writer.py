from __future__ import annotations

import asyncio
from typing import Any

from supabase import Client


def append_ledger_event(
    supabase: Client,
    *,
    appraisal_id: str,
    pipeline_run_id: str,
    node_name: str,
    schema_version: str,
    input_refs: dict[str, Any],
    output: dict[str, Any] | None,
    confidence_summary: dict[str, Any] | None,
    status: str,
    error: str | None = None,
) -> None:
    """
    Append a ledger event (synchronous version).
    For async usage, wrap in asyncio.to_thread().
    """
    supabase.table("ledger_events").insert(
        {
            "appraisal_id": appraisal_id,
            "pipeline_run_id": pipeline_run_id,
            "node_name": node_name,
            "schema_version": schema_version,
            "input_refs": input_refs,
            "output": output,
            "confidence_summary": confidence_summary,
            "status": status,
            "error": error,
        }
    ).execute()


async def append_ledger_event_async(
    supabase: Client,
    *,
    appraisal_id: str,
    pipeline_run_id: str,
    node_name: str,
    schema_version: str,
    input_refs: dict[str, Any],
    output: dict[str, Any] | None,
    confidence_summary: dict[str, Any] | None,
    status: str,
    error: str | None = None,
) -> None:
    """
    Append a ledger event (async version).
    Wraps synchronous call in asyncio.to_thread().
    """
    await asyncio.to_thread(
        append_ledger_event,
        supabase,
        appraisal_id=appraisal_id,
        pipeline_run_id=pipeline_run_id,
        node_name=node_name,
        schema_version=schema_version,
        input_refs=input_refs,
        output=output,
        confidence_summary=confidence_summary,
        status=status,
        error=error,
    )


def fetch_ledger_events(
    supabase: Client,
    *,
    appraisal_id: str,
    pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch ledger events (synchronous version).
    For async usage, wrap in asyncio.to_thread().
    """
    query = (
        supabase.table("ledger_events")
        .select("*")
        .eq("appraisal_id", appraisal_id)
        .order("timestamp", desc=False)
    )
    if pipeline_run_id:
        query = query.eq("pipeline_run_id", pipeline_run_id)
    result = query.execute()
    return list(result.data or [])


async def fetch_ledger_events_async(
    supabase: Client,
    *,
    appraisal_id: str,
    pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch ledger events (async version).
    Wraps synchronous call in asyncio.to_thread().
    """
    return await asyncio.to_thread(
        fetch_ledger_events,
        supabase,
        appraisal_id=appraisal_id,
        pipeline_run_id=pipeline_run_id,
    )
