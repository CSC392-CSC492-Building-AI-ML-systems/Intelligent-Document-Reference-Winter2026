"""Job state helpers for tracking and transitioning job lifecycle."""

from typing import Optional

from jobs import Job, JobQueue


def transition_state(
    queue: JobQueue,
    job_id: int,
    new_status: str,
    error: Optional[str] = None,
) -> Job:
    """Move a job to *new_status*.

    Args:
        queue: The JobQueue instance.
        job_id: Row id of the job.
        new_status: Target status (``"completed"`` or ``"failed"``).
        error: Error message (only used when *new_status* is ``"failed"``).

    Returns:
        The updated Job.

    Raises:
        ValueError: If *new_status* is not ``"completed"`` or ``"failed"``.
    """
    if new_status == "completed":
        return queue.complete(job_id)
    if new_status == "failed":
        return queue.fail(job_id, error or "Unknown error")
    raise ValueError(f"Unsupported transition to '{new_status}'")


def should_retry(job: Job) -> bool:
    """Return True if the job has remaining retry attempts.

    Args:
        job: The Job to inspect.

    Returns:
        Whether the job's attempts are below max_attempts.
    """
    return job.attempts < job.max_attempts
