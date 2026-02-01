import asyncio
import json
import os
import sys
from pathlib import Path

# Add shared packages to Python path for imports
current_file = Path(__file__).resolve()
shared_path = current_file.parent.parent.parent.parent / "shared"

if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.settings import get_settings
from app.storage import upload_artifact_bytes, create_signed_url
from app.supabase_client import get_supabase_client
from app.upload import (
    enforce_photo_limits,
    enforce_total_size,
    generate_short_id_from_db,
    new_uuid,
    normalize_image_bytes,
    validate_content_types,
    validate_photos_for_duplicates,
)
from app.validation import (
    validate_idempotency_key,
    validate_notes_length,
    sanitize_notes,
)
from app.metadata_schema import validate_metadata
from app.pipeline import run_pipeline_agentic_async, generate_embeddings_async
from app.vision import extract_from_photo
from ledger.ledger.writer import fetch_ledger_events


class CreateAppraisalRequest(BaseModel):
    metadata_json: dict
    notes_raw: str | None = None


app = FastAPI(title="Vehicle Appraisal Pre-Check API", version="0.1.0")

# Configure CORS
cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
cors_origins = cors_origins_raw.split(",") if cors_origins_raw else ["*"]

if cors_origins == ["*"]:
    allow_origins = ["*"]
else:
    processed_origins = []
    for origin in cors_origins:
        origin = origin.strip()
        if not origin:
            continue
        if "." not in origin and not origin.startswith(("http://", "https://")) and origin != "*":
            processed_origins.append(f"https://{origin}.onrender.com")
        elif not origin.startswith(("http://", "https://")) and "." in origin:
            processed_origins.append(f"https://{origin}")
        else:
            processed_origins.append(origin)
    allow_origins = processed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_appraisal_id(appraisal_ref: str) -> tuple[str | None, str | None]:
    """Resolve an appraisal reference (either short_id or UUID) to both UUID and short_id."""
    supabase = get_supabase_client()
    
    try:
        if len(appraisal_ref) == 4:
            result = (
                supabase.table("appraisals")
                .select("id, short_id")
                .eq("short_id", appraisal_ref.upper())
                .execute()
            )
        else:
            result = (
                supabase.table("appraisals")
                .select("id, short_id")
                .eq("id", appraisal_ref)
                .execute()
            )
        
        if result.data and len(result.data) > 0:
            return result.data[0]["id"], result.data[0]["short_id"]
        return None, None
    except Exception:
        return None, None


def run_vision_extraction_sync(appraisal_id: str, artifact_id: str):
    """Run vision extraction synchronously (for BackgroundTasks)."""
    try:
        supabase = get_supabase_client()
        
        # Fetch artifact
        artifact_res = (
            supabase.table("artifacts")
            .select("*")
            .eq("id", artifact_id)
            .eq("appraisal_id", appraisal_id)
            .single()
            .execute()
        )
        
        if not artifact_res.data:
            return
        
        artifact = artifact_res.data
        storage_path = artifact.get("storage_path")
        
        if not storage_path:
            return
        
        # Generate signed URL
        signed_url = create_signed_url(supabase, storage_path, expires_in_seconds=3600)
        
        # Extract vision
        vision_result = extract_from_photo(signed_url, artifact_id)
        
        # Update artifact with vision output
        supabase.table("artifacts").update({
            "vision_output_json": vision_result,
            "vision_extraction_status": "completed"
        }).eq("id", artifact_id).execute()
        
    except Exception as e:
        # Update artifact with error status
        try:
            supabase = get_supabase_client()
            supabase.table("artifacts").update({
                "vision_extraction_status": "failed",
                "vision_output_json": {"error": str(e)}
            }).eq("id", artifact_id).execute()
        except Exception:
            pass


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe - is the service running?"""
    _ = get_settings()
    return {"ok": True}


@app.get("/readyz")
async def readiness_check() -> dict:
    """Readiness probe - can the service handle requests?"""
    checks = {}
    
    # Check Supabase connection
    try:
        supabase = get_supabase_client()
        supabase.table("appraisals").select("id").limit(1).execute()
        checks["supabase"] = True
    except Exception:
        checks["supabase"] = False
    
    # Check OpenAI connection (basic check)
    try:
        from app.llm_client import get_llm_client
        _ = get_llm_client()
        checks["openai"] = True
    except Exception:
        checks["openai"] = False
    
    # Check RAG availability (if enabled)
    if os.getenv("ENABLE_RAG", "false").lower() == "true":
        try:
            # Try to import RAG modules
            from rag.rag.embeddings import generate_embedding
            checks["rag"] = True
        except Exception:
            checks["rag"] = False
    else:
        checks["rag"] = None  # Not enabled
    
    all_healthy = all(v for v in checks.values() if v is not None)
    
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }


@app.post("/api/appraisals/create")
async def create_appraisal_only(
    request: CreateAppraisalRequest = Body(...)
) -> JSONResponse:
    """Create an appraisal without photos. Photos can be added later via /photos/upload endpoint."""
    metadata_obj = request.metadata_json
    notes_raw = request.notes_raw
    
    # Validate metadata schema
    validated_metadata, metadata_errors = validate_metadata(metadata_obj)
    if metadata_errors:
        return JSONResponse(
            status_code=400,
            content={"error": "Metadata validation failed", "details": metadata_errors}
        )
    
    # Validate notes length and sanitize
    is_valid, error_msg = validate_notes_length(notes_raw)
    if not is_valid:
        return JSONResponse(status_code=400, content={"error": error_msg})
    notes_raw = sanitize_notes(notes_raw)

    supabase = get_supabase_client()
    appraisal_id = new_uuid()
    
    # Generate short_id with proper error handling
    try:
        short_id = generate_short_id_from_db(supabase)
    except Exception as e:
        # If short_id generation fails completely, return a helpful error
        error_msg = str(e).lower()
        if '429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests - Database is temporarily rate-limited. Please try again in a few seconds."}
            )
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate appraisal ID: {str(e)}"}
        )

    # Create appraisal record
    try:
        insert = (
            supabase.table("appraisals")
            .insert(
                {
                    "id": appraisal_id,
                    "short_id": short_id,
                    "metadata_json": validated_metadata,
                    "notes_raw": notes_raw,
                    "latest_run_id": None,
                }
            )
            .execute()
        )
        if not getattr(insert, "data", None):
            return JSONResponse(status_code=500, content={"error": "Failed to create appraisal"})
    except APIError as e:
        # Check for rate limit errors in the insert operation
        error_message = str(e).lower()
        status_code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
        
        if status_code == 429 or '429' in str(e) or 'rate limit' in error_message or 'too many requests' in error_message:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests - Database is temporarily rate-limited. Please try again in a few seconds."}
            )
        return JSONResponse(status_code=500, content={"error": f"DB error creating appraisal: {e.message}"})

    return JSONResponse(status_code=201, content={"id": short_id, "uuid": appraisal_id})


@app.post("/api/appraisals/{appraisal_id}/photos/upload")
async def upload_single_photo(
    appraisal_id: str,
    photo: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> JSONResponse:
    """Upload a single photo and trigger background vision extraction."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    appraisal_id = uuid
    
    # Validate photo
    validate_content_types([photo])
    
    # Check if photo size is reasonable (10MB per photo)
    if photo.size and photo.size > 10 * 1024 * 1024:
        return JSONResponse(status_code=400, content={"error": "Photo size exceeds 10MB"})
    
    supabase = get_supabase_client()
    
    # Upload photo
    artifact_id = new_uuid()
    raw = await photo.read()
    content, content_type = normalize_image_bytes(raw, photo.content_type)
    
    try:
        # Upload to storage
        def upload_and_insert():
            storage_path = upload_artifact_bytes(
                supabase=supabase,
                appraisal_id=appraisal_id,
                artifact_id=artifact_id,
                content=content,
                content_type=content_type,
                filename=photo.filename,
            )
            # Insert artifact record with pending status
            supabase.table("artifacts").insert(
                {
                    "id": artifact_id,
                    "appraisal_id": appraisal_id,
                    "storage_path": storage_path,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    "vision_extraction_status": "pending",
                }
            ).execute()
            return storage_path
        
        storage_path = await asyncio.to_thread(upload_and_insert)
        
        # Trigger vision extraction using BackgroundTasks (reliable for FastAPI)
        background_tasks.add_task(run_vision_extraction_sync, appraisal_id, artifact_id)
        
        return JSONResponse(
            status_code=201,
            content={
                "artifact_id": artifact_id,
                "storage_path": storage_path,
                "message": "Photo uploaded successfully. Vision extraction started in background."
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Upload failed: {str(e)}"})


@app.post("/api/appraisals")
async def create_appraisal(
    metadata_json: str = Form(default="{}"),
    notes_raw: str | None = Form(default=None),
    photos: list[UploadFile] = File(...),
) -> JSONResponse:
    """Create an appraisal with photos."""
    # Validate and parse metadata
    try:
        metadata_obj = json.loads(metadata_json or "{}")
        if not isinstance(metadata_obj, dict):
            raise ValueError("metadata_json must be a JSON object")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "metadata_json must be a JSON object"})
    
    # Validate metadata schema
    validated_metadata, metadata_errors = validate_metadata(metadata_obj)
    if metadata_errors:
        return JSONResponse(
            status_code=400,
            content={"error": "Metadata validation failed", "details": metadata_errors}
        )
    
    # Validate notes length and sanitize
    is_valid, error_msg = validate_notes_length(notes_raw)
    if not is_valid:
        return JSONResponse(status_code=400, content={"error": error_msg})
    notes_raw = sanitize_notes(notes_raw)

    # Validate photos
    enforce_photo_limits(photos)
    validate_content_types(photos)
    enforce_total_size(photos)
    
    # Check for duplicate photos
    try:
        validate_photos_for_duplicates(photos)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})

    supabase = get_supabase_client()
    appraisal_id = new_uuid()
    
    # Generate short_id with proper error handling
    try:
        short_id = generate_short_id_from_db(supabase)
    except Exception as e:
        # If short_id generation fails completely, return a helpful error
        error_msg = str(e).lower()
        if '429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests - Database is temporarily rate-limited. Please try again in a few seconds."}
            )
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate appraisal ID: {str(e)}"}
        )

    # Create appraisal record
    try:
        insert = (
            supabase.table("appraisals")
            .insert(
                {
                    "id": appraisal_id,
                    "short_id": short_id,
                    "metadata_json": validated_metadata,
                    "notes_raw": notes_raw,
                    "latest_run_id": None,
                }
            )
            .execute()
        )
        if not getattr(insert, "data", None):
            return JSONResponse(status_code=500, content={"error": "Failed to create appraisal"})
    except APIError as e:
        # Check for rate limit errors in the insert operation
        error_message = str(e).lower()
        status_code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
        
        if status_code == 429 or '429' in str(e) or 'rate limit' in error_message or 'too many requests' in error_message:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests - Database is temporarily rate-limited. Please try again in a few seconds."}
            )
        return JSONResponse(status_code=500, content={"error": f"DB error creating appraisal: {e.message}"})

    # Upload artifacts in parallel
    async def upload_single_photo(photo: UploadFile) -> dict:
        artifact_id = new_uuid()
        raw = await photo.read()
        content, content_type = normalize_image_bytes(raw, photo.content_type)
        
        def upload_and_insert():
            storage_path = upload_artifact_bytes(
                supabase=supabase,
                appraisal_id=appraisal_id,
                artifact_id=artifact_id,
                content=content,
                content_type=content_type,
                filename=photo.filename,
            )
            try:
                supabase.table("artifacts").insert(
                    {
                        "id": artifact_id,
                        "appraisal_id": appraisal_id,
                        "storage_path": storage_path,
                        "content_type": content_type,
                        "size_bytes": len(content),
                        "vision_extraction_status": "pending",
                    }
                ).execute()
                return {"success": True, "artifact_id": artifact_id}
            except APIError as e:
                return {"success": False, "error": f"DB error creating artifact row: {e.message}"}
        
        result = await asyncio.to_thread(upload_and_insert)
        if not result.get("success"):
            raise Exception(result.get("error", "Upload failed"))
        return result
    
    # Upload all photos concurrently
    try:
        upload_tasks = [upload_single_photo(photo) for photo in photos]
        await asyncio.gather(*upload_tasks)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error uploading photos: {str(e)}"})

    return JSONResponse(status_code=201, content={"id": short_id, "uuid": appraisal_id})


@app.post("/api/appraisals/{appraisal_id}/run")
async def run_appraisal(
    appraisal_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> JSONResponse:
    """
    Run agentic pipeline for an appraisal (async only).
    Note: Sync mode removed for Render free tier compatibility (30s timeout limit).
    """
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    appraisal_id = uuid
    
    # Validate idempotency key format
    is_valid, error_msg = validate_idempotency_key(idempotency_key)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    supabase = get_supabase_client()

    # Insert pipeline_run or reuse existing by idempotency_key
    try:
        existing = (
            supabase.table("pipeline_runs")
            .select("id")
            .eq("idempotency_key", idempotency_key)
            .eq("appraisal_id", appraisal_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            pipeline_run_id = existing.data[0]["id"]
        else:
            pipeline_run_id = new_uuid()
            supabase.table("pipeline_runs").insert(
                {
                    "id": pipeline_run_id,
                    "appraisal_id": appraisal_id,
                    "status": "PENDING",
                    "idempotency_key": idempotency_key,
                    "outputs_version": "v1",
                }
            ).execute()
    except APIError as e:
        return JSONResponse(status_code=500, content={"error": f"DB error creating pipeline_run: {e.message}"})

    # Use BackgroundTasks for reliable background execution
    background_tasks.add_task(run_pipeline_agentic_async, pipeline_run_id, appraisal_id)
    
    return JSONResponse(
        status_code=202,
        content={
            "pipeline_run_id": pipeline_run_id,
            "status": "enqueued",
            "execution_mode": "agentic",
            "message": "Pipeline execution started in background. Use /run/{run_id}/status to check progress."
        }
    )


@app.get("/api/appraisals/{appraisal_id}/run/{run_id}/status")
async def get_run_status(appraisal_id: str, run_id: str) -> JSONResponse:
    """Get pipeline run status for polling."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    
    supabase = get_supabase_client()
    
    try:
        run_res = (
            supabase.table("pipeline_runs")
            .select("*")
            .eq("id", run_id)
            .eq("appraisal_id", uuid)
            .single()
            .execute()
        )
        
        if not run_res.data:
            return JSONResponse(status_code=404, content={"error": f"Pipeline run '{run_id}' not found"})
        
        return JSONResponse(content=run_res.data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/appraisals/{appraisal_id}")
async def get_appraisal_latest(appraisal_id: str) -> JSONResponse:
    """Get appraisal with latest run results."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        raise HTTPException(status_code=404, detail=f"Appraisal '{appraisal_id}' not found")
    appraisal_id = uuid
    
    supabase = get_supabase_client()

    appraisal = (
        supabase.table("appraisals")
        .select("id, short_id, metadata_json, notes_raw, latest_run_id")
        .eq("id", appraisal_id)
        .limit(1)
        .execute()
    )
    if not appraisal.data:
        raise HTTPException(status_code=404, detail="Appraisal not found")

    latest_run_id = appraisal.data[0]["latest_run_id"]
    latest_run = None
    if latest_run_id:
        run_res = (
            supabase.table("pipeline_runs")
            .select("*")
            .eq("id", latest_run_id)
            .limit(1)
            .execute()
        )
        latest_run = run_res.data[0] if run_res.data else None

    return JSONResponse(
        content={
            "appraisal": appraisal.data[0],
            "latest_run": latest_run,
        }
    )


@app.get("/api/appraisals/{appraisal_id}/runs")
async def get_appraisal_runs(appraisal_id: str) -> JSONResponse:
    """Get all pipeline runs for an appraisal."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    appraisal_id = uuid
    
    supabase = get_supabase_client()
    runs = (
        supabase.table("pipeline_runs")
        .select("*")
        .eq("appraisal_id", appraisal_id)
        .order("created_at", desc=True)
        .execute()
    )
    return JSONResponse(content={"runs": runs.data or []})


@app.get("/api/appraisals/{appraisal_id}/photos")
async def get_appraisal_photos(appraisal_id: str) -> JSONResponse:
    """Get all photos/artifacts for an appraisal with signed URLs."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    appraisal_id = uuid
    
    supabase = get_supabase_client()
    
    artifacts_data = supabase.table("artifacts").select("*").eq("appraisal_id", appraisal_id).execute()
    artifacts = artifacts_data.data or []
    
    # Create signed URLs for artifacts
    for artifact in artifacts:
        storage_path = artifact.get("storage_path")
        if storage_path:
            try:
                artifact["signed_url"] = create_signed_url(supabase, storage_path)
            except Exception:
                artifact["signed_url"] = None
    
    return JSONResponse(content={"photos": artifacts})


@app.get("/api/appraisals/{appraisal_id}/ledger")
async def get_appraisal_ledger(appraisal_id: str) -> JSONResponse:
    """Get ledger events for an appraisal."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    appraisal_id = uuid
    
    supabase = get_supabase_client()
    events = fetch_ledger_events(supabase, appraisal_id=appraisal_id)
    return JSONResponse(content={"events": events})


@app.get("/api/appraisals/{appraisal_id}/ledger/download")
async def download_appraisal_ledger(appraisal_id: str) -> Response:
    """Download ledger as JSON attachment for the appraisal."""
    uuid, short_id = resolve_appraisal_id(appraisal_id)
    if not uuid:
        return JSONResponse(status_code=404, content={"error": f"Appraisal '{appraisal_id}' not found"})
    
    supabase = get_supabase_client()
    events = fetch_ledger_events(supabase, appraisal_id=uuid)
    
    return Response(
        content=json.dumps({"events": events}, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="ledger-{short_id}.json"'}
    )
