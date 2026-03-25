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
    job_queue: Optional[Any] = None
    scheduler: Optional[Any] = None
    watcher: Optional[Any] = None
    settings_store: Optional[Any] = None
