"""Job queue implementation with priority and deduplication support."""
import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from queue import PriorityQueue
import threading


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Job model for queue processing."""
    job_type: str
    payload: Dict[str, Any]
    priority: int = 2  # Default normal priority
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0
    
    def __lt__(self, other):
        """Compare jobs by priority (higher priority first) and creation time."""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority first
        return self.created_at < other.created_at  # Earlier jobs first if same priority
    
    def get_dedup_key(self) -> str:
        """Generate deduplication key based on job type and payload."""
        payload_str = json.dumps(self.payload, sort_keys=True)
        key = f"{self.job_type}:{payload_str}"
        return hashlib.md5(key.encode()).hexdigest()


class JobQueue:
    """Thread-safe priority job queue with deduplication."""
    
    def __init__(self, max_size: int = 10000, dedup_window: float = 60.0):
        """
        Initialize job queue.
        
        Args:
            max_size: Maximum number of jobs in queue
            dedup_window: Time window (seconds) for deduplication
        """
        self._queue: PriorityQueue = PriorityQueue(maxsize=max_size)
        self._jobs: Dict[str, Job] = {}  # job_id -> Job
        self._dedup_map: Dict[str, str] = {}  # dedup_key -> job_id
        self._lock = threading.RLock()
        self._dedup_window = dedup_window
        self._max_size = max_size
    
    def enqueue(self, job: Job) -> Optional[str]:
        """
        Add a job to the queue with deduplication.
        
        Args:
            job: Job to enqueue
            
        Returns:
            job_id if enqueued, None if deduplicated
        """
        with self._lock:
            # Check deduplication
            dedup_key = job.get_dedup_key()
            
            # Clean old dedup entries
            self._clean_dedup_map()
            
            # Check if similar job exists
            if dedup_key in self._dedup_map:
                existing_job_id = self._dedup_map[dedup_key]
                existing_job = self._jobs.get(existing_job_id)
                
                # Only deduplicate if existing job is still pending
                if existing_job and existing_job.status == JobStatus.PENDING:
                    # Update existing job with newer one if priority is higher
                    if job.priority > existing_job.priority:
                        existing_job.priority = job.priority
                        existing_job.payload = job.payload
                        existing_job.created_at = job.created_at
                    return None  # Deduplicated
            
            # Check queue size
            if self._queue.qsize() >= self._max_size:
                raise ValueError(f"Queue is full (max size: {self._max_size})")
            
            # Add to queue
            self._queue.put(job)
            self._jobs[job.job_id] = job
            self._dedup_map[dedup_key] = job.job_id
            
            return job.job_id
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Job]:
        """
        Remove and return the highest priority job from the queue.
        
        Args:
            timeout: Maximum time to wait for a job (None = blocking)
            
        Returns:
            Job if available, None if timeout
        """
        try:
            job = self._queue.get(timeout=timeout)
            with self._lock:
                # Update job status
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                
                # Remove from dedup map
                dedup_key = job.get_dedup_key()
                if dedup_key in self._dedup_map and self._dedup_map[dedup_key] == job.job_id:
                    del self._dedup_map[dedup_key]
            
            return job
        except Exception:
            return None
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        with self._lock:
            return self._jobs.get(job_id)
    
    def update_job_status(self, job_id: str, status: JobStatus, error: Optional[str] = None):
        """Update job status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                if error:
                    job.error = error
                if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    job.completed_at = time.time()
    
    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            stats = {
                "total": len(self._jobs),
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "queue_size": self._queue.qsize()
            }
            
            for job in self._jobs.values():
                stats[job.status.value] += 1
            
            return stats
    
    def _clean_dedup_map(self):
        """Remove old entries from deduplication map."""
        current_time = time.time()
        with self._lock:
            keys_to_remove = []
            for dedup_key, job_id in self._dedup_map.items():
                job = self._jobs.get(job_id)
                if not job or (current_time - job.created_at) > self._dedup_window:
                    keys_to_remove.append(dedup_key)
            
            for key in keys_to_remove:
                del self._dedup_map[key]
    
    def clear(self):
        """Clear all jobs from queue."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Exception:
                    break
            self._jobs.clear()
            self._dedup_map.clear()


# Global queue instance
_global_queue: Optional[JobQueue] = None
_queue_lock = threading.Lock()


def get_queue() -> JobQueue:
    """Get or create global job queue instance."""
    global _global_queue
    if _global_queue is None:
        with _queue_lock:
            if _global_queue is None:
                _global_queue = JobQueue()
    return _global_queue


def enqueue(job: Job) -> Optional[str]:
    """
    Enqueue a job to the global queue.
    
    Args:
        job: Job to enqueue
        
    Returns:
        job_id if enqueued, None if deduplicated
    """
    queue = get_queue()
    return queue.enqueue(job)
