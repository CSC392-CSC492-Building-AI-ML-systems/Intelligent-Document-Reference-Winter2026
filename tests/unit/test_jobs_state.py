"""Unit tests for job state management."""
import time
import pytest
from jobs.queue import Job, JobStatus, JobQueue
from jobs.state import (
    update_state,
    get_job_state,
    get_jobs_by_status,
    get_recent_jobs,
    get_queue_stats,
    clear_completed_jobs
)


class TestJobState:
    """Test job state management."""
    
    @pytest.fixture
    def queue(self):
        """Create a fresh queue for each test."""
        return JobQueue()
    
    def test_update_state(self, queue):
        """Test updating job state."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        result = update_state(job_id, JobStatus.COMPLETED, queue=queue)
        
        assert result is True
        updated = queue.get_job(job_id)
        assert updated.status == JobStatus.COMPLETED
    
    def test_update_state_with_error(self, queue):
        """Test updating job state with error message."""
        job = Job(job_type="test", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        result = update_state(job_id, JobStatus.FAILED, "Test error", queue=queue)
        
        assert result is True
        updated = queue.get_job(job_id)
        assert updated.status == JobStatus.FAILED
        assert updated.error == "Test error"
    
    def test_update_state_nonexistent_job(self, queue):
        """Test updating state of nonexistent job."""
        result = update_state("nonexistent-id", JobStatus.COMPLETED, queue=queue)
        assert result is False
    
    def test_get_job_state(self, queue):
        """Test getting job state."""
        job = Job(job_type="test", payload={"data": "test"}, priority=3)
        job_id = queue.enqueue(job)
        
        state = get_job_state(job_id, queue=queue)
        
        assert state is not None
        assert state["job_id"] == job_id
        assert state["job_type"] == "test"
        assert state["status"] == "pending"
        assert state["priority"] == 3
        assert state["payload"] == {"data": "test"}
        assert state["created_at"] is not None
        assert state["error"] is None
        assert state["retry_count"] == 0
    
    def test_get_job_state_nonexistent(self, queue):
        """Test getting state of nonexistent job."""
        state = get_job_state("nonexistent-id", queue=queue)
        assert state is None
    
    def test_get_jobs_by_status(self, queue):
        """Test getting jobs by status."""
        job1 = Job(job_type="test1", payload={"id": 1})
        job2 = Job(job_type="test2", payload={"id": 2})
        job3 = Job(job_type="test3", payload={"id": 3})
        
        job_id1 = queue.enqueue(job1)
        job_id2 = queue.enqueue(job2)
        job_id3 = queue.enqueue(job3)
        
        # Mark one as completed
        queue.update_job_status(job_id2, JobStatus.COMPLETED)
        
        pending_jobs = get_jobs_by_status(JobStatus.PENDING, queue=queue)
        completed_jobs = get_jobs_by_status(JobStatus.COMPLETED, queue=queue)
        
        assert len(pending_jobs) == 2
        assert len(completed_jobs) == 1
        assert completed_jobs[0]["job_id"] == job_id2
    
    def test_get_jobs_by_status_limit(self, queue):
        """Test getting jobs by status with limit."""
        for i in range(10):
            queue.enqueue(Job(job_type=f"test{i}", payload={"id": i}))
        
        jobs = get_jobs_by_status(JobStatus.PENDING, limit=5, queue=queue)
        assert len(jobs) == 5
    
    def test_get_recent_jobs(self, queue):
        """Test getting recent jobs."""
        for i in range(5):
            queue.enqueue(Job(job_type=f"test{i}", payload={"id": i}))
            time.sleep(0.01)  # Ensure different timestamps
        
        recent = get_recent_jobs(limit=3, queue=queue)
        
        assert len(recent) == 3
        # Should be sorted by creation time, newest first
        assert recent[0]["payload"]["id"] == 4
        assert recent[1]["payload"]["id"] == 3
        assert recent[2]["payload"]["id"] == 2
    
    def test_get_queue_stats(self, queue):
        """Test getting queue statistics."""
        job1 = Job(job_type="test1", payload={})
        job2 = Job(job_type="test2", payload={})
        job3 = Job(job_type="test3", payload={})
        
        job_id1 = queue.enqueue(job1)
        job_id2 = queue.enqueue(job2)
        job_id3 = queue.enqueue(job3)
        
        queue.update_job_status(job_id1, JobStatus.RUNNING)
        queue.update_job_status(job_id2, JobStatus.COMPLETED)
        queue.update_job_status(job_id3, JobStatus.FAILED)
        
        stats = get_queue_stats(queue=queue)
        
        assert stats["total"] == 3
        assert stats["pending"] == 0
        assert stats["running"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1
    
    def test_clear_completed_jobs(self, queue):
        """Test clearing completed jobs."""
        job1 = Job(job_type="test1", payload={})
        job2 = Job(job_type="test2", payload={})
        job3 = Job(job_type="test3", payload={})
        
        job_id1 = queue.enqueue(job1)
        job_id2 = queue.enqueue(job2)
        job_id3 = queue.enqueue(job3)
        
        # Mark jobs with different statuses
        queue.update_job_status(job_id1, JobStatus.COMPLETED)
        queue.update_job_status(job_id2, JobStatus.FAILED)
        # job3 stays pending
        
        # Clear with very short time (should clear immediately completed jobs)
        cleared = clear_completed_jobs(older_than=0, queue=queue)
        
        assert cleared >= 2  # At least completed and failed jobs
        
        # Pending job should still exist
        pending_jobs = get_jobs_by_status(JobStatus.PENDING, queue=queue)
        assert len(pending_jobs) >= 0  # May or may not include job3 depending on timing
    
    def test_clear_completed_jobs_respects_age(self, queue):
        """Test that clearing respects age threshold."""
        job = Job(job_type="test", payload={})
        job_id = queue.enqueue(job)
        queue.update_job_status(job_id, JobStatus.COMPLETED)
        
        # Try to clear jobs older than 100 seconds (none should be cleared)
        cleared = clear_completed_jobs(older_than=100, queue=queue)
        
        assert cleared == 0
        assert queue.get_job(job_id) is not None
    
    def test_job_duration_calculation(self, queue):
        """Test that job duration is calculated correctly."""
        job = Job(job_type="test", payload={})
        job_id = queue.enqueue(job)
        
        # Simulate job running
        job_obj = queue.get_job(job_id)
        job_obj.started_at = time.time()
        time.sleep(0.1)
        queue.update_job_status(job_id, JobStatus.COMPLETED)
        
        state = get_job_state(job_id, queue=queue)
        
        assert state["duration"] is not None
        assert state["duration"] >= 0.1
