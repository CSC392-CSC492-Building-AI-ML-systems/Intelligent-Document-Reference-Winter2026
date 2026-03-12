"""Job control endpoints.

Provides enqueue, list, and status-lookup for indexing jobs.
"""

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import get_context
from backend.schemas import JobEnqueueRequest, JobListResponse, JobResponse
from core.context import AppContext
from jobs import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_response(job: Job) -> JobResponse:
    """Convert a Job dataclass to a Pydantic response."""
    return JobResponse(**asdict(job))


@router.post("/enqueue", response_model=JobResponse)
async def enqueue_job(
    req: JobEnqueueRequest,
    ctx: AppContext = Depends(get_context),
):
    """Enqueue an indexing job (called by the Web UI)."""
    if ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    job = ctx.scheduler.schedule(
        file_path=req.file_path,
        source=req.source,
        priority=req.priority,
    )
    return _job_to_response(job)


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = None,
    ctx: AppContext = Depends(get_context),
):
    """List jobs, optionally filtered by status."""
    if ctx.job_queue is None:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    jobs = ctx.job_queue.list_jobs(status=status)
    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    ctx: AppContext = Depends(get_context),
):
    """Get a single job by id."""
    if ctx.job_queue is None:
        raise HTTPException(status_code=503, detail="Job queue not initialized")

    job = ctx.job_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_response(job)
