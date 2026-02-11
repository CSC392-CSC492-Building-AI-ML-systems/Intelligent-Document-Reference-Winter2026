"""Unit tests for job worker."""
import asyncio
import pytest
from jobs.queue import Job, JobStatus, JobQueue
from jobs.worker import Worker


class TestWorker:
    """Test job worker functionality."""
    
    @pytest.fixture
    def queue(self):
        """Create a fresh queue for each test."""
        return JobQueue()
    
    @pytest.fixture
    def worker(self, queue):
        """Create a worker instance."""
        return Worker(queue=queue, poll_interval=0.01)
    
    @pytest.mark.asyncio
    async def test_register_handler(self, worker):
        """Test registering a job handler."""
        handler_called = False
        
        async def test_handler(job):
            nonlocal handler_called
            handler_called = True
        
        worker.register_handler("test_job", test_handler)
        
        assert "test_job" in worker._handlers
    
    @pytest.mark.asyncio
    async def test_process_job_success(self, worker, queue):
        """Test successful job processing."""
        result_data = []
        
        async def test_handler(job):
            result_data.append(job.payload["data"])
        
        worker.register_handler("test_job", test_handler)
        
        job = Job(job_type="test_job", payload={"data": "test_value"})
        job_id = queue.enqueue(job)
        
        # Start worker
        await worker.start()
        
        # Wait for job to be processed
        await asyncio.sleep(0.2)
        
        # Stop worker
        await worker.stop()
        
        # Verify job was processed
        assert len(result_data) == 1
        assert result_data[0] == "test_value"
        
        # Verify job status
        processed_job = queue.get_job(job_id)
        assert processed_job.status == JobStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_process_job_failure(self, worker, queue):
        """Test job processing with failure."""
        async def failing_handler(job):
            raise ValueError("Test error")
        
        worker.register_handler("test_job", failing_handler)
        worker._max_retries = 0  # Disable retries for this test
        
        job = Job(job_type="test_job", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        await worker.start()
        await asyncio.sleep(0.2)
        await worker.stop()
        
        # Verify job failed
        processed_job = queue.get_job(job_id)
        assert processed_job.status == JobStatus.FAILED
        assert "Test error" in processed_job.error
    
    @pytest.mark.asyncio
    async def test_process_job_retry(self, worker, queue):
        """Test job retry on failure."""
        attempt_count = []
        
        async def flaky_handler(job):
            attempt_count.append(1)
            if len(attempt_count) < 3:
                raise ValueError("Temporary error")
            # Success on third attempt
        
        worker.register_handler("test_job", flaky_handler)
        worker._max_retries = 3
        worker._retry_delay = 0.05
        
        job = Job(job_type="test_job", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        await worker.start()
        await asyncio.sleep(1.0)  # Wait for retries
        await worker.stop()
        
        # Should succeed after retries
        assert len(attempt_count) == 3
        processed_job = queue.get_job(job_id)
        assert processed_job.status == JobStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_process_job_no_handler(self, worker, queue):
        """Test processing job with no registered handler."""
        job = Job(job_type="unknown_job", payload={"data": "test"})
        job_id = queue.enqueue(job)
        
        await worker.start()
        await asyncio.sleep(0.2)
        await worker.stop()
        
        # Job should fail
        processed_job = queue.get_job(job_id)
        assert processed_job.status == JobStatus.FAILED
        assert "No handler registered" in processed_job.error
    
    @pytest.mark.asyncio
    async def test_process_multiple_jobs(self, worker, queue):
        """Test processing multiple jobs in sequence."""
        results = []
        
        async def test_handler(job):
            results.append(job.payload["id"])
        
        worker.register_handler("test_job", test_handler)
        
        # Enqueue multiple jobs
        for i in range(5):
            queue.enqueue(Job(job_type="test_job", payload={"id": i}))
        
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()
        
        # All jobs should be processed
        assert len(results) == 5
        assert set(results) == {0, 1, 2, 3, 4}
    
    @pytest.mark.asyncio
    async def test_process_jobs_by_priority(self, worker, queue):
        """Test that jobs are processed by priority."""
        results = []
        
        async def test_handler(job):
            results.append(job.payload["priority"])
            await asyncio.sleep(0.05)  # Slow processing to ensure ordering
        
        worker.register_handler("test_job", test_handler)
        
        # Enqueue jobs with different priorities
        queue.enqueue(Job(job_type="test_job", payload={"priority": 1}, priority=1))
        queue.enqueue(Job(job_type="test_job", payload={"priority": 3}, priority=3))
        queue.enqueue(Job(job_type="test_job", payload={"priority": 2}, priority=2))
        
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()
        
        # Should process in priority order (high to low)
        assert results == [3, 2, 1]
    
    @pytest.mark.asyncio
    async def test_worker_stop(self, worker):
        """Test stopping the worker."""
        await worker.start()
        assert worker._running is True
        
        await worker.stop()
        assert worker._running is False
