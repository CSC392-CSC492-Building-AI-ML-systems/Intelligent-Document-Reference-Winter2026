"""Unit tests for job scheduler."""
import pytest
from jobs.scheduler import (
    schedule,
    schedule_index_job,
    schedule_delete_job,
    schedule_batch
)
from jobs.queue import JobQueue, JobStatus


class TestScheduler:
    """Test job scheduler functionality."""
    
    @pytest.fixture
    def queue(self):
        """Create a fresh queue for each test."""
        return JobQueue()
    
    def test_schedule_job(self, queue):
        """Test scheduling a job."""
        job_id = schedule(
            job_type="test_job",
            payload={"data": "test"},
            priority=2,
            queue=queue
        )
        
        assert job_id is not None
        assert queue.size() == 1
        
        job = queue.get_job(job_id)
        assert job.job_type == "test_job"
        assert job.payload == {"data": "test"}
        assert job.priority == 2
    
    def test_schedule_deduplication(self, queue):
        """Test that scheduler deduplicates jobs."""
        job_id1 = schedule(
            job_type="test_job",
            payload={"path": "/test/file.txt"},
            queue=queue
        )
        
        job_id2 = schedule(
            job_type="test_job",
            payload={"path": "/test/file.txt"},
            queue=queue
        )
        
        assert job_id1 is not None
        assert job_id2 is None
        assert queue.size() == 1
    
    def test_schedule_index_job(self, queue):
        """Test scheduling an index job."""
        job_id = schedule_index_job("/path/to/file.txt", priority=2)
        
        # Clean up global queue
        from jobs.queue import get_queue
        global_queue = get_queue()
        
        assert job_id is not None
        job = global_queue.get_job(job_id)
        assert job.job_type == "index_document"
        assert job.payload["path"] == "/path/to/file.txt"
        assert job.priority == 2
        
        # Clean up
        global_queue.clear()
    
    def test_schedule_delete_job(self, queue):
        """Test scheduling a delete job."""
        job_id = schedule_delete_job("/path/to/file.txt", priority=3)
        
        # Clean up global queue
        from jobs.queue import get_queue
        global_queue = get_queue()
        
        assert job_id is not None
        job = global_queue.get_job(job_id)
        assert job.job_type == "delete_document"
        assert job.payload["path"] == "/path/to/file.txt"
        assert job.priority == 3
        
        # Clean up
        global_queue.clear()
    
    def test_schedule_batch(self, queue):
        """Test scheduling multiple jobs in batch."""
        jobs = [
            {"job_type": "test1", "payload": {"id": 1}, "priority": 2},
            {"job_type": "test2", "payload": {"id": 2}, "priority": 3},
            {"job_type": "test3", "payload": {"id": 3}},  # Default priority
        ]
        
        job_ids = schedule_batch(jobs)
        
        # Clean up global queue
        from jobs.queue import get_queue
        global_queue = get_queue()
        
        assert len(job_ids) == 3
        assert all(jid is not None for jid in job_ids)
        
        # Verify jobs
        job1 = global_queue.get_job(job_ids[0])
        assert job1.job_type == "test1"
        assert job1.priority == 2
        
        job2 = global_queue.get_job(job_ids[1])
        assert job2.job_type == "test2"
        assert job2.priority == 3
        
        job3 = global_queue.get_job(job_ids[2])
        assert job3.job_type == "test3"
        assert job3.priority == 2  # Default
        
        # Clean up
        global_queue.clear()
    
    def test_schedule_batch_with_deduplication(self, queue):
        """Test that batch scheduling handles deduplication."""
        jobs = [
            {"job_type": "test", "payload": {"path": "/file.txt"}},
            {"job_type": "test", "payload": {"path": "/file.txt"}},  # Duplicate
            {"job_type": "test", "payload": {"path": "/other.txt"}},
        ]
        
        job_ids = schedule_batch(jobs)
        
        # Clean up global queue
        from jobs.queue import get_queue
        global_queue = get_queue()
        
        assert len(job_ids) == 3
        assert job_ids[0] is not None
        assert job_ids[1] is None  # Deduplicated
        assert job_ids[2] is not None
        
        # Clean up
        global_queue.clear()
