"""DB-backed job queue with priority ordering and deduplication."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

PRIORITY_WATCHER = 1
PRIORITY_UI = 10


@dataclass
class Job:
    """Represents a single indexing job."""

    id: int
    file_path: str
    source: str
    priority: int
    status: str
    attempts: int
    max_attempts: int
    error_message: Optional[str]
    created_at: str
    updated_at: str


class JobQueue:
    """SQLite-backed FIFO-with-priority job queue.

    Shares the same database file as ``UnifiedDatabase`` but opens its
    own plain ``sqlite3`` connections (no sqlite-vec extension loaded).
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_table(self) -> None:
        """Create the jobs table if it does not exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL DEFAULT 'watcher',
                    priority INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
                    ON jobs (status, priority DESC, created_at ASC)
            """)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        """Convert a sqlite3.Row to a Job dataclass."""
        return Job(**dict(row))

    @staticmethod
    def _now() -> str:
        """Return current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def enqueue(
        self,
        file_path: str,
        source: str = "watcher",
        priority: Optional[int] = None,
    ) -> Job:
        """Add a job or bump priority if it already exists.

        Deduplication: if a *queued* job for the same ``file_path``
        already exists the row is updated (priority may be raised,
        source/timestamp refreshed).  Jobs that are ``running``,
        ``completed``, or ``failed`` are replaced with a fresh
        ``queued`` entry via ON CONFLICT.

        Args:
            file_path: Absolute path of the file to index.
            source: ``"watcher"`` or ``"ui"``.
            priority: Explicit priority.  Defaults to PRIORITY_UI for
                ``"ui"`` source, PRIORITY_WATCHER otherwise.

        Returns:
            The created or updated Job.
        """
        if priority is None:
            priority = PRIORITY_UI if source == "ui" else PRIORITY_WATCHER

        now = self._now()
        conn = self._get_conn()
        try:
            # Check for an existing queued job for this path
            row = conn.execute(
                "SELECT * FROM jobs WHERE file_path = ? AND status = 'queued'",
                (file_path,),
            ).fetchone()

            if row:
                # Bump priority if new request is higher; always refresh ts
                new_priority = max(row["priority"], priority)
                conn.execute(
                    """UPDATE jobs
                       SET priority = ?, source = ?, updated_at = ?
                     WHERE id = ?""",
                    (new_priority, source, now, row["id"]),
                )
                conn.commit()
                updated = conn.execute(
                    "SELECT * FROM jobs WHERE id = ?", (row["id"],)
                ).fetchone()
                return self._row_to_job(updated)

            # No queued duplicate — insert (or replace completed/failed)
            conn.execute(
                """INSERT INTO jobs
                       (file_path, source, priority, status, attempts,
                        max_attempts, error_message, created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', 0, 3, NULL, ?, ?)
                   ON CONFLICT(file_path) DO UPDATE SET
                       source     = excluded.source,
                       priority   = excluded.priority,
                       status     = 'queued',
                       attempts   = 0,
                       error_message = NULL,
                       updated_at = excluded.updated_at""",
                (file_path, source, priority, now, now),
            )
            conn.commit()
            inserted = conn.execute(
                "SELECT * FROM jobs WHERE file_path = ?", (file_path,)
            ).fetchone()
            return self._row_to_job(inserted)
        finally:
            conn.close()

    def dequeue(self) -> Optional[Job]:
        """Atomically pop the highest-priority queued job.

        Sets status to ``running`` and increments ``attempts``.

        Returns:
            The Job now marked as running, or None if the queue is empty.
        """
        now = self._now()
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT * FROM jobs
                    WHERE status = 'queued'
                 ORDER BY priority DESC, created_at ASC
                    LIMIT 1""",
            ).fetchone()
            if row is None:
                return None

            conn.execute(
                """UPDATE jobs
                      SET status = 'running', attempts = attempts + 1,
                          updated_at = ?
                    WHERE id = ?""",
                (now, row["id"]),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (row["id"],)
            ).fetchone()
            return self._row_to_job(updated)
        finally:
            conn.close()

    def complete(self, job_id: int) -> Job:
        """Mark a job as completed.

        Args:
            job_id: The row id of the job.

        Returns:
            The updated Job.
        """
        now = self._now()
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE jobs
                      SET status = 'completed', error_message = NULL,
                          updated_at = ?
                    WHERE id = ?""",
                (now, job_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row)
        finally:
            conn.close()

    def fail(self, job_id: int, error: str) -> Job:
        """Record a failure and auto-retry if attempts remain.

        If ``attempts < max_attempts`` the status is reset to ``queued``
        so the worker will pick it up again.  Otherwise the status stays
        ``failed``.

        Args:
            job_id: The row id of the job.
            error: Human-readable error description.

        Returns:
            The updated Job.
        """
        now = self._now()
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise ValueError(f"Job {job_id} not found")

            if row["attempts"] < row["max_attempts"]:
                # Retry: reset to queued
                conn.execute(
                    """UPDATE jobs
                          SET status = 'queued', error_message = ?,
                              updated_at = ?
                        WHERE id = ?""",
                    (error, now, job_id),
                )
            else:
                # Exhausted retries
                conn.execute(
                    """UPDATE jobs
                          SET status = 'failed', error_message = ?,
                              updated_at = ?
                        WHERE id = ?""",
                    (error, now, job_id),
                )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return self._row_to_job(updated)
        finally:
            conn.close()

    def get_job(self, job_id: int) -> Optional[Job]:
        """Fetch a single job by id.

        Args:
            job_id: The row id.

        Returns:
            The Job or None if not found.
        """
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None
        finally:
            conn.close()

    def list_jobs(self, status: Optional[str] = None) -> List[Job]:
        """List jobs, optionally filtered by status.

        Args:
            status: If provided, only return jobs with this status.

        Returns:
            List of Job objects ordered by priority desc, then age.
        """
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """SELECT * FROM jobs WHERE status = ?
                    ORDER BY priority DESC, created_at ASC""",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY priority DESC, created_at ASC"
                ).fetchall()
            return [self._row_to_job(r) for r in rows]
        finally:
            conn.close()

    def pending_count(self) -> int:
        """Return count of queued + running jobs."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM jobs "
                "WHERE status IN ('queued', 'running')"
            ).fetchone()
            return row["cnt"]
        finally:
            conn.close()
