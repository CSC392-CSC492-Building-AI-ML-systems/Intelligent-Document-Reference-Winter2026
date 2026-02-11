"""Integration tests for watcher -> queue -> indexing flow."""
import asyncio
import time
import pytest
import tempfile
from pathlib import Path
from jobs.queue import JobQueue, JobStatus
from jobs.worker import Worker
from jobs.scheduler import schedule
from watcher.events import FileEvent
from watcher.debounce import DebounceHandler


class TestWatcherQueueIntegration:
    """Test integration between watcher, queue, and worker."""
    
    @pytest.fixture
    def queue(self):
        """Create a fresh queue."""
        return JobQueue()
    
    @pytest.fixture
    def worker(self, queue):
        """Create a worker."""
        return Worker(queue=queue, poll_interval=0.01)
    
    @pytest.mark.asyncio
    async def test_file_change_triggers_indexing_job(self, queue, worker):
        """Test that file changes trigger indexing jobs."""
        indexed_files = []
        
        async def mock_index_handler(job):
            """Mock indexer that records which files were indexed."""
            path = job.payload.get('path')
            indexed_files.append(path)
        
        worker.register_handler("index_document", mock_index_handler)
        
        # Schedule an indexing job (simulating watcher behavior)
        job_id = schedule(
            job_type="index_document",
            payload={"path": "/test/document.txt"},
            priority=2,
            queue=queue
        )
        
        # Start worker to process jobs
        await worker.start()
        await asyncio.sleep(0.2)
        await worker.stop()
        
        # Verify file was indexed
        assert len(indexed_files) == 1
        assert "/test/document.txt" in indexed_files
        
        # Verify job completed
        job = queue.get_job(job_id)
        assert job.status == JobStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_multiple_file_changes_with_deduplication(self, queue, worker):
        """Test that multiple changes to same file are deduplicated."""
        indexed_files = []
        
        async def mock_index_handler(job):
            path = job.payload.get('path')
            indexed_files.append(path)
        
        worker.register_handler("index_document", mock_index_handler)
        
        # Simulate rapid file changes (should be deduplicated)
        schedule(
            job_type="index_document",
            payload={"path": "/test/document.txt"},
            priority=2,
            queue=queue
        )
        schedule(
            job_type="index_document",
            payload={"path": "/test/document.txt"},
            priority=2,
            queue=queue
        )
        schedule(
            job_type="index_document",
            payload={"path": "/test/document.txt"},
            priority=2,
            queue=queue
        )
        
        await worker.start()
        await asyncio.sleep(0.3)
        await worker.stop()
        
        # Should only index once due to deduplication
        assert len(indexed_files) == 1
    
    @pytest.mark.asyncio
    async def test_debounce_integration(self):
        """Test debounce handler integration with job scheduling."""
        scheduled_jobs = []
        
        def schedule_callback(event: FileEvent):
            """Callback that schedules jobs."""
            from jobs.scheduler import schedule_index_job
            job_id = schedule_index_job(event.path, priority=2)
            scheduled_jobs.append((event.path, job_id))
        
        debouncer = DebounceHandler(delay=0.1, callback=schedule_callback)
        
        # Simulate rapid file changes
        debouncer.add_event(FileEvent(path="/test/file.txt", type="modified"))
        debouncer.add_event(FileEvent(path="/test/file.txt", type="modified"))
        debouncer.add_event(FileEvent(path="/test/file.txt", type="modified"))
        
        # Wait for debounce
        time.sleep(0.2)
        
        # Should have scheduled only one job
        assert len(scheduled_jobs) == 1
        assert scheduled_jobs[0][0] == "/test/file.txt"
        
        # Cleanup
        from jobs.queue import get_queue
        get_queue().clear()
    
    @pytest.mark.asyncio
    async def test_priority_processing(self, queue, worker):
        """Test that high-priority jobs are processed first."""
        processed_order = []
        
        async def mock_handler(job):
            processed_order.append(job.payload['name'])
            await asyncio.sleep(0.05)  # Slow processing
        
        worker.register_handler("index_document", mock_handler)
        
        # Schedule jobs with different priorities
        schedule(
            job_type="index_document",
            payload={"path": "/low.txt", "name": "low"},
            priority=1,
            queue=queue
        )
        schedule(
            job_type="index_document",
            payload={"path": "/high.txt", "name": "high"},
            priority=3,
            queue=queue
        )
        schedule(
            job_type="index_document",
            payload={"path": "/normal.txt", "name": "normal"},
            priority=2,
            queue=queue
        )
        
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()
        
        # Should process in priority order
        assert processed_order == ['high', 'normal', 'low']
    
    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, queue, worker):
        """Test error handling and retry logic."""
        attempts = []
        
        async def flaky_handler(job):
            attempts.append(len(attempts))
            if len(attempts) < 2:
                raise ValueError("Temporary failure")
            # Succeed on second attempt
        
        worker.register_handler("index_document", flaky_handler)
        worker._max_retries = 3
        worker._retry_delay = 0.05
        
        job_id = schedule(
            job_type="index_document",
            payload={"path": "/test/file.txt"},
            priority=2,
            queue=queue
        )
        
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()
        
        # Should have retried and succeeded
        assert len(attempts) == 2
        
        job = queue.get_job(job_id)
        assert job.status == JobStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_concurrent_job_processing(self, queue, worker):
        """Test that jobs are processed sequentially by a single worker."""
        processing = []
        
        async def tracking_handler(job):
            processing.append('start')
            await asyncio.sleep(0.05)
            processing.append('end')
        
        worker.register_handler("index_document", tracking_handler)
        
        # Schedule multiple jobs
        for i in range(3):
            schedule(
                job_type="index_document",
                payload={"path": f"/test/file{i}.txt"},
                priority=2,
                queue=queue
            )
        
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()
        
        # Should have processed all jobs sequentially
        assert len(processing) == 6
        # Pattern should be start, end, start, end, start, end
        assert processing == ['start', 'end', 'start', 'end', 'start', 'end']
