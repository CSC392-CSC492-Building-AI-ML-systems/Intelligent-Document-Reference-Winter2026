"""Scheduler and deduplication logic for job management."""
import logging
from typing import Dict, Any, Optional

from jobs.queue import Job, JobQueue, get_queue, enqueue as queue_enqueue


logger = logging.getLogger(__name__)


def schedule(
    job_type: str,
    payload: Dict[str, Any],
    priority: int = 2,
    queue: Optional[JobQueue] = None
) -> Optional[str]:
    """
    Schedule a job with deduplication.
    
    Args:
        job_type: Type of job to schedule
        payload: Job payload data
        priority: Job priority (1=low, 2=normal, 3=high)
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        job_id if scheduled, None if deduplicated
    """
    job = Job(
        job_type=job_type,
        payload=payload,
        priority=priority
    )
    
    if queue:
        job_id = queue.enqueue(job)
    else:
        job_id = queue_enqueue(job)
    
    if job_id:
        logger.info(f"Scheduled job {job_id} (type: {job_type}, priority: {priority})")
    else:
        logger.debug(f"Job deduplicated (type: {job_type}, payload: {payload})")
    
    return job_id


def schedule_index_job(path: str, priority: int = 2) -> Optional[str]:
    """
    Schedule a document indexing job.
    
    Args:
        path: Path to the document to index
        priority: Job priority
        
    Returns:
        job_id if scheduled, None if deduplicated
    """
    return schedule(
        job_type="index_document",
        payload={"path": path},
        priority=priority
    )


def schedule_delete_job(path: str, priority: int = 2) -> Optional[str]:
    """
    Schedule a document deletion job.
    
    Args:
        path: Path to the document to delete
        priority: Job priority
        
    Returns:
        job_id if scheduled, None if deduplicated
    """
    return schedule(
        job_type="delete_document",
        payload={"path": path},
        priority=priority
    )


def schedule_batch(jobs: list[Dict[str, Any]]) -> list[Optional[str]]:
    """
    Schedule multiple jobs in batch.
    
    Args:
        jobs: List of job specifications with 'job_type', 'payload', and optional 'priority'
        
    Returns:
        List of job_ids (None for deduplicated jobs)
    """
    job_ids = []
    for job_spec in jobs:
        job_id = schedule(
            job_type=job_spec['job_type'],
            payload=job_spec['payload'],
            priority=job_spec.get('priority', 2)
        )
        job_ids.append(job_id)
    
    scheduled_count = sum(1 for jid in job_ids if jid is not None)
    logger.info(f"Scheduled {scheduled_count}/{len(jobs)} jobs in batch")
    
    return job_ids
