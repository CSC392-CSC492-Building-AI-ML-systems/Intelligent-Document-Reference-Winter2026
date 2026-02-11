"""Job state persistence and query helpers."""
import logging
import time
from typing import Optional, List, Dict, Any

from jobs.queue import Job, JobStatus, get_queue, JobQueue


logger = logging.getLogger(__name__)


def update_state(
    job_id: str,
    status: JobStatus,
    error: Optional[str] = None,
    queue: Optional[JobQueue] = None
) -> bool:
    """
    Update job state.
    
    Args:
        job_id: Job identifier
        status: New job status
        error: Optional error message
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        True if updated successfully, False otherwise
    """
    q = queue or get_queue()
    
    job = q.get_job(job_id)
    if not job:
        logger.warning(f"Job {job_id} not found")
        return False
    
    q.update_job_status(job_id, status, error)
    logger.info(f"Updated job {job_id} status to {status.value}")
    
    return True


def get_job_state(job_id: str, queue: Optional[JobQueue] = None) -> Optional[Dict[str, Any]]:
    """
    Get current state of a job.
    
    Args:
        job_id: Job identifier
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        Dictionary with job state or None if not found
    """
    q = queue or get_queue()
    job = q.get_job(job_id)
    
    if not job:
        return None
    
    return {
        'job_id': job.job_id,
        'job_type': job.job_type,
        'status': job.status.value,
        'priority': job.priority,
        'payload': job.payload,
        'created_at': job.created_at,
        'started_at': job.started_at,
        'completed_at': job.completed_at,
        'error': job.error,
        'retry_count': job.retry_count,
        'duration': _calculate_duration(job)
    }


def get_jobs_by_status(
    status: JobStatus,
    limit: int = 100,
    queue: Optional[JobQueue] = None
) -> List[Dict[str, Any]]:
    """
    Get jobs by status.
    
    Args:
        status: Job status to filter by
        limit: Maximum number of jobs to return
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        List of job state dictionaries
    """
    q = queue or get_queue()
    jobs = []
    
    with q._lock:
        for job in q._jobs.values():
            if job.status == status:
                jobs.append(get_job_state(job.job_id, q))
                if len(jobs) >= limit:
                    break
    
    return jobs


def get_recent_jobs(
    limit: int = 50,
    queue: Optional[JobQueue] = None
) -> List[Dict[str, Any]]:
    """
    Get most recent jobs.
    
    Args:
        limit: Maximum number of jobs to return
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        List of job state dictionaries, sorted by creation time (newest first)
    """
    q = queue or get_queue()
    
    with q._lock:
        all_jobs = list(q._jobs.values())
    
    # Sort by creation time, newest first
    all_jobs.sort(key=lambda j: j.created_at, reverse=True)
    
    return [get_job_state(job.job_id, q) for job in all_jobs[:limit]]


def get_queue_stats(queue: Optional[JobQueue] = None) -> Dict[str, Any]:
    """
    Get queue statistics.
    
    Args:
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        Dictionary with queue statistics
    """
    q = queue or get_queue()
    stats = q.get_stats()
    
    # Note: 'uptime' tracking would require storing worker start time
    # This is a placeholder that should be implemented with proper worker lifecycle tracking
    
    return stats


def clear_completed_jobs(
    older_than: float = 3600,
    queue: Optional[JobQueue] = None
) -> int:
    """
    Clear completed jobs older than specified time.
    
    Args:
        older_than: Clear jobs completed more than this many seconds ago
        queue: Optional queue instance (uses global queue if None)
        
    Returns:
        Number of jobs cleared
    """
    q = queue or get_queue()
    current_time = time.time()
    cleared = 0
    
    with q._lock:
        jobs_to_remove = []
        for job_id, job in q._jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                if job.completed_at and (current_time - job.completed_at) > older_than:
                    jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del q._jobs[job_id]
            cleared += 1
    
    logger.info(f"Cleared {cleared} completed jobs older than {older_than}s")
    return cleared


def _calculate_duration(job: Job) -> Optional[float]:
    """Calculate job duration in seconds."""
    if job.started_at is None:
        return None
    
    end_time = job.completed_at or time.time()
    return end_time - job.started_at
