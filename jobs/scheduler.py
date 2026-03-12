"""Scheduler: normalizes paths, deduplicates, and enqueues jobs."""

import logging
import os
from typing import Optional

from jobs import PRIORITY_UI, PRIORITY_WATCHER, Job, JobQueue

logger = logging.getLogger(__name__)


class Scheduler:
    """Normalizes paths, deduplicates, and forwards to the job queue."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    def schedule(
        self,
        file_path: str,
        source: str = "watcher",
        priority: Optional[int] = None,
    ) -> Job:
        """Normalize *file_path* and enqueue an indexing job.

        If a ``running`` job already exists for the same file the
        request is still accepted — the queue's UNIQUE-based dedup will
        handle it on the next cycle when that job completes or fails.

        Args:
            file_path: Raw path (may contain ``~`` or relative segments).
            source: ``"watcher"`` or ``"ui"``.
            priority: Override default priority for the source.

        Returns:
            The created or updated Job.
        """
        clean_path = os.path.abspath(os.path.expanduser(file_path))

        if priority is None:
            priority = PRIORITY_UI if source == "ui" else PRIORITY_WATCHER

        job = self._queue.enqueue(clean_path, source=source, priority=priority)
        logger.info(
            "Scheduled job %s for %s (source=%s, priority=%d, status=%s)",
            job.id,
            clean_path,
            source,
            job.priority,
            job.status,
        )
        return job
