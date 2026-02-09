"""Pydantic request/response schemas (stubs)."""

from typing import List, Optional

from pydantic import BaseModel, Field


class WatchPathRequest(BaseModel):
    path: str
    excluded_files: Optional[List[str]] = Field(default_factory=list)


class WatchPathResponse(BaseModel):
    status: str
    active_paths: List[dict]
