"""
Model execution routes.

POST /api/v1/run-model          → submit a job, returns job_id immediately
GET  /api/v1/job-status/{id}    → poll job status
GET  /api/v1/results/{id}       → fetch completed result metadata
GET  /api/v1/results/{id}/download/{filename} → download an output CSV
GET  /api/v1/available-policies → list policy dataset files
GET  /api/v1/available-scenarios → list scenario files
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.model import (
    AvailableFile,
    AvailableFilesResponse,
    JobResultResponse,
    JobStatus,
    JobStatusResponse,
    RunModelRequest,
)
from app.services import job_store as _store
from app.services import model_service

router = APIRouter(prefix="/api/v1", tags=["Model Execution"])

_BASE = Path(settings.base_dir)


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------

@router.post(
    "/run-model",
    summary="Submit a model run job",
    status_code=202,
)
async def run_model(request: RunModelRequest) -> dict:
    job_id = str(uuid.uuid4())
    model_service.submit_job(job_id, request)
    return {"job_id": job_id, "status": "pending"}


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

@router.get(
    "/job-status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job execution status",
)
async def job_status(job_id: str) -> JobStatusResponse:
    rec = _store.job_store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    elapsed: float | None = None
    if rec.started_at and rec.completed_at:
        elapsed = (rec.completed_at - rec.started_at).total_seconds()

    return JobStatusResponse(
        job_id=rec.job_id,
        status=rec.status,
        created_at=rec.created_at,
        started_at=rec.started_at,
        completed_at=rec.completed_at,
        elapsed_seconds=elapsed,
        progress=rec.progress,
        error=rec.error,
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@router.get(
    "/results/{job_id}",
    response_model=JobResultResponse,
    summary="Get result metadata for a completed job",
)
async def get_results(job_id: str) -> JobResultResponse:
    rec = _store.job_store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if rec.status not in (JobStatus.completed, JobStatus.failed):
        raise HTTPException(
            status_code=409,
            detail=f"Job is still {rec.status.value}. Poll /job-status/{job_id}.",
        )

    return JobResultResponse(
        job_id=rec.job_id,
        status=rec.status,
        output_dir=rec.output_dir or "",
        scenarios=rec.scenarios,
        output_files=rec.output_files,
        total_elapsed_seconds=rec.total_elapsed_seconds,
        n_policies=rec.n_policies,
    )


@router.get(
    "/results/{job_id}/download/{filename}",
    summary="Download an output file from a completed job",
)
async def download_result(job_id: str, filename: str) -> FileResponse:
    rec = _store.job_store.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if rec.status != JobStatus.completed:
        raise HTTPException(status_code=409, detail="Job not completed yet")

    output_dir = Path(rec.output_dir)
    # Prevent path traversal
    target = (output_dir / filename).resolve()
    if not str(target).startswith(str(output_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    return FileResponse(
        path=str(target),
        filename=filename,
        media_type="text/csv",
    )


# ---------------------------------------------------------------------------
# Discovery helpers (used by React form dropdowns)
# ---------------------------------------------------------------------------

@router.get(
    "/available-policies",
    response_model=AvailableFilesResponse,
    summary="List available policy dataset files",
)
async def available_policies() -> AvailableFilesResponse:
    policy_dir = _BASE / "policy_data"
    files = _list_files(policy_dir, suffixes={".csv", ".parquet"})
    return AvailableFilesResponse(files=files)


@router.get(
    "/available-scenarios",
    response_model=AvailableFilesResponse,
    summary="List available scenario/sensitivity files",
)
async def available_scenarios() -> AvailableFilesResponse:
    sen_dir = _BASE / "sen_fac"
    files = _list_files(sen_dir, suffixes={".csv"})
    return AvailableFilesResponse(files=files)


@router.get(
    "/jobs",
    summary="List all known job IDs",
)
async def list_jobs() -> dict:
    return {"job_ids": _store.job_store.list_ids()}


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _list_files(directory: Path, suffixes: set) -> List[AvailableFile]:
    if not directory.is_dir():
        return []
    result: List[AvailableFile] = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in suffixes:
            result.append(
                AvailableFile(
                    key=f.name,
                    path=str(f.relative_to(_BASE)),
                    size_bytes=f.stat().st_size,
                )
            )
    return result
