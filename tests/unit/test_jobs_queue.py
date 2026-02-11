"""Unit tests for job queue functionality."""
import time
import pytest
from jobs.queue import Job, JobStatus, JobQueue, get_queue


class TestJob:
    """Test Job model."""
    
    def test_job_creation(self):
        """Test creating a job."""
        job = Job(
            job_type="test_job",
            payload={"data": "test"},
            priority=2
        )
        
        assert job.job_type == "test_job"
        assert job.payload == {"data": "test"}
        assert job.priority == 2
        assert job.status == JobStatus.PENDING
        assert job.job_id is not None
        assert job.retry_count == 0
    
    def test_job_comparison_priority(self):
        """Test job comparison by priority."""
        job_low = Job(job_type="test", payload={}, priority=1)
        job_high = Job(job_type="test", payload={}, priority=3)
        
        # Higher priority should be "less than" (comes first)
        assert job_high < job_low
    
    def test_job_comparison_time(self):
        """Test job comparison by creation time when priority is equal."""
        job1 = Job(job_type="test", payload={}, priority=2)
        time.sleep(0.01)
        job2 = Job(job_type="test", payload={}, priority=2)
        
        # Earlier job should come first
        assert job1 < job2
    
    def test_job_dedup_key(self):
        """Test deduplication key generation."""
        job1 = Job(job_type="test", payload={"path": "/test/file.txt"})
        job2 = Job(job_type="test", payload={"path": "/test/file.txt"})
        job3 = Job(job_type="test", payload={"path": "/test/other.txt"})
        
        # Same type and payload should have same dedup key
        assert job1.get_dedup_key() == job2.get_dedup_key()
        
        # Different payload should have different dedup key
        assert job1.get_dedup_key() != job3.get_dedup_key()


class TestJobQueue:
    """Test JobQueue functionality."""
    
    @pytest.fixture
    def queue(self):
        """Create a fresh queue for each test."""
        return JobQueue(max_size=100, dedup_window=5.0)
    
    def test_enqueue_job(self, queue):
        """Test enqueueing a job."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        assert job_id == job.job_id
        assert queue.size() == 1
    
    def test_dequeue_job(self, queue):
        """Test dequeueing a job."""
        job = Job(job_type="test", payload={"data": "test"})
        queue.enqueue(job)
        
        dequeued = queue.dequeue(timeout=0.1)
        
        assert dequeued is not None
        assert dequeued.job_id == job.job_id
        assert dequeued.status == JobStatus.RUNNING
        assert dequeued.started_at is not None
    
    def test_priority_order(self, queue):
        """Test that jobs are dequeued in priority order."""
        job_low = Job(job_type="test", payload={"id": 1}, priority=1)
        job_medium = Job(job_type="test", payload={"id": 2}, priority=2)
        job_high = Job(job_type="test", payload={"id": 3}, priority=3)
        
        # Enqueue in random order
        queue.enqueue(job_medium)
        queue.enqueue(job_low)
        queue.enqueue(job_high)
        
        # Should dequeue in priority order (high to low)
        assert queue.dequeue(timeout=0.1).payload["id"] == 3
        assert queue.dequeue(timeout=0.1).payload["id"] == 2
        assert queue.dequeue(timeout=0.1).payload["id"] == 1
    
    def test_deduplication(self, queue):
        """Test job deduplication."""
        job1 = Job(job_type="test", payload={"path": "/test/file.txt"}, priority=2)
        job2 = Job(job_type="test", payload={"path": "/test/file.txt"}, priority=2)
        
        # First job should be enqueued
        job_id1 = queue.enqueue(job1)
        assert job_id1 is not None
        
        # Second identical job should be deduplicated
        job_id2 = queue.enqueue(job2)
        assert job_id2 is None
        
        # Queue should only have one job
        assert queue.size() == 1
    
    def test_deduplication_priority_update(self, queue):
        """Test that deduplication updates priority if higher."""
        job1 = Job(job_type="test", payload={"path": "/test/file.txt"}, priority=2)
        job2 = Job(job_type="test", payload={"path": "/test/file.txt"}, priority=3)
        
        queue.enqueue(job1)
        queue.enqueue(job2)
        
        # Should still have one job with updated priority
        assert queue.size() == 1
        
        dequeued = queue.dequeue(timeout=0.1)
        assert dequeued.priority == 3
    
    def test_get_job(self, queue):
        """Test getting a job by ID."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        retrieved = queue.get_job(job_id)
        assert retrieved is not None
        assert retrieved.job_id == job_id
    
    def test_update_job_status(self, queue):
        """Test updating job status."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        queue.update_job_status(job_id, JobStatus.COMPLETED)
        
        updated = queue.get_job(job_id)
        assert updated.status == JobStatus.COMPLETED
        assert updated.completed_at is not None
    
    def test_update_job_with_error(self, queue):
        """Test updating job status with error."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        queue.update_job_status(job_id, JobStatus.FAILED, "Test error")
        
        updated = queue.get_job(job_id)
        assert updated.status == JobStatus.FAILED
        assert updated.error == "Test error"
    
    def test_queue_stats(self, queue):
        """Test getting queue statistics."""
        job1 = Job(job_type="test", payload={"id": 1})
        job2 = Job(job_type="test", payload={"id": 2})
        
        queue.enqueue(job1)
        queue.enqueue(job2)
        
        stats = queue.get_stats()
        assert stats["total"] == 2
        assert stats["pending"] == 2
        assert stats["queue_size"] == 2
    
    def test_queue_full(self):
        """Test queue max size limit."""
        queue = JobQueue(max_size=2)
        
        queue.enqueue(Job(job_type="test", payload={"id": 1}))
        queue.enqueue(Job(job_type="test", payload={"id": 2}))
        
        with pytest.raises(ValueError, match="Queue is full"):
            queue.enqueue(Job(job_type="test", payload={"id": 3}))
    
    def test_clear_queue(self, queue):
        """Test clearing the queue."""
        queue.enqueue(Job(job_type="test", payload={"id": 1}))
        queue.enqueue(Job(job_type="test", payload={"id": 2}))
        
        queue.clear()
        
        assert queue.size() == 0
        assert queue.get_stats()["total"] == 0


class TestGlobalQueue:
    """Test global queue instance."""
    
    def test_get_queue_singleton(self):
        """Test that get_queue returns the same instance."""
        queue1 = get_queue()
        queue2 = get_queue()
        
        assert queue1 is queue2
