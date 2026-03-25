"""Application context (lightweight DI container).

Stores initialized subsystems and configuration for runtime routing.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AppContext:
    settings: Any
    db: Optional[Any] = None
    embedding_client: Optional[Any] = None
    inference_client: Optional[Any] = None
    runtime_preferences: Optional[dict] = None
    job_queue: Optional[Any] = None
    scheduler: Optional[Any] = None
    watcher: Optional[Any] = None
    settings_store: Optional[Any] = None
    reindex_in_progress: bool = False
