"""Pydantic request/response schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class WatchPathRequest(BaseModel):
    path: str
    excluded_files: Optional[List[str]] = Field(default_factory=list)


class WatchPathResponse(BaseModel):
    status: str
    active_paths: List[dict]


class SyncPathsRequest(BaseModel):
    """Inclusion list paths to sync with monitor_config (paths not in this list get is_active=0)."""

    paths: List[str] = []


class JobEnqueueRequest(BaseModel):
    """Request body for POST /jobs/enqueue."""

    file_path: str
    source: str = Field(default="ui", pattern="^(ui|watcher)$")
    priority: Optional[int] = None


class JobResponse(BaseModel):
    """Single job representation returned by the API."""

    id: int
    file_path: str
    source: str
    priority: int
    status: str
    attempts: int
    max_attempts: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    """Response for GET /jobs/."""

    jobs: List[JobResponse]
    total: int
