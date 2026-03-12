"""Unit tests for the jobs subsystem (queue, scheduler, state, worker)."""

import asyncio
from pathlib import Path
from typing import Generator, List

import pytest

from db.unified import UnifiedDatabase
from jobs import (
    PRIORITY_UI,
    PRIORITY_WATCHER,
    Job,
    JobQueue,
    Scheduler,
    Worker,
    should_retry,
    transition_state,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Provide a temporary database path for an isolated job queue."""
    return str(tmp_path / "test_jobs.db")


@pytest.fixture
def queue(db_path: str) -> Generator[JobQueue, None, None]:
    """Provide an initialized JobQueue backed by a temp DB."""
    yield JobQueue(db_path)


@pytest.fixture
def scheduler(queue: JobQueue) -> Scheduler:
    """Provide a Scheduler wrapping the test queue."""
    return Scheduler(queue)


class TestJobQueue:
    """Tests for the core JobQueue class."""

    def test_enqueue_creates_job(self, queue: JobQueue) -> None:
        """Enqueue should create a job with status 'queued'."""
        job = queue.enqueue("/tmp/test.txt", source="ui")
        assert job.status == "queued"
        assert job.file_path == "/tmp/test.txt"
        assert job.source == "ui"
        assert job.priority == PRIORITY_UI
        assert job.attempts == 0

    def test_enqueue_watcher_default_priority(self, queue: JobQueue) -> None:
        """Watcher-sourced jobs should get PRIORITY_WATCHER by default."""
        job = queue.enqueue("/tmp/watch.txt", source="watcher")
        assert job.priority == PRIORITY_WATCHER

    def test_dequeue_returns_highest_priority(self, queue: JobQueue) -> None:
        """Dequeue should return the UI job before the watcher job."""
        queue.enqueue("/tmp/low.txt", source="watcher")
        queue.enqueue("/tmp/high.txt", source="ui")

        first = queue.dequeue()
        assert first is not None
        assert first.file_path == "/tmp/high.txt"
        assert first.status == "running"
        assert first.attempts == 1

        second = queue.dequeue()
        assert second is not None
        assert second.file_path == "/tmp/low.txt"

    def test_dequeue_empty_returns_none(self, queue: JobQueue) -> None:
        """Dequeue on an empty queue should return None."""
        assert queue.dequeue() is None

    def test_dedup_same_path_queued(self, queue: JobQueue) -> None:
        """Enqueueing the same path twice should not create two rows."""
        job1 = queue.enqueue("/tmp/dup.txt", source="watcher")
        job2 = queue.enqueue("/tmp/dup.txt", source="ui")

        # Same row, priority bumped to UI level
        assert job1.id == job2.id
        assert job2.priority == PRIORITY_UI
        assert job2.source == "ui"

        # Only one job in the queue
        all_jobs = queue.list_jobs()
        assert len(all_jobs) == 1

    def test_dedup_replaces_completed(self, queue: JobQueue) -> None:
        """Re-enqueueing a completed file should reset it to queued."""
        job = queue.enqueue("/tmp/done.txt", source="watcher")
        queue.dequeue()
        queue.complete(job.id)

        # Now re-enqueue the same path
        new_job = queue.enqueue("/tmp/done.txt", source="ui")
        assert new_job.status == "queued"
        assert new_job.attempts == 0
        assert new_job.priority == PRIORITY_UI

    def test_complete(self, queue: JobQueue) -> None:
        """Completing a running job should set status to 'completed'."""
        queue.enqueue("/tmp/c.txt")
        job = queue.dequeue()
        done = queue.complete(job.id)
        assert done.status == "completed"
        assert done.error_message is None

    def test_fail_with_retry(self, queue: JobQueue) -> None:
        """Failing a job with remaining attempts resets to 'queued'."""
        queue.enqueue("/tmp/retry.txt")
        job = queue.dequeue()  # attempt 1
        assert job.attempts == 1

        failed = queue.fail(job.id, "transient error")
        assert failed.status == "queued"
        assert failed.error_message == "transient error"

    def test_fail_exhausted(self, queue: JobQueue) -> None:
        """Failing a job that exhausted max_attempts stays 'failed'."""
        queue.enqueue("/tmp/perm.txt")

        for i in range(3):
            job = queue.dequeue()
            assert job is not None
            queue.fail(job.id, f"error #{i + 1}")

        final = queue.get_job(job.id)
        assert final.status == "failed"
        assert final.attempts == 3

    def test_list_jobs_filter(self, queue: JobQueue) -> None:
        """list_jobs(status=...) should filter correctly."""
        queue.enqueue("/tmp/a.txt")
        queue.enqueue("/tmp/b.txt")
        queue.dequeue()  # moves /tmp/b.txt or /tmp/a.txt to running

        queued = queue.list_jobs(status="queued")
        running = queue.list_jobs(status="running")
        assert len(queued) == 1
        assert len(running) == 1

    def test_pending_count(self, queue: JobQueue) -> None:
        """pending_count should include queued + running jobs."""
        queue.enqueue("/tmp/x.txt")
        queue.enqueue("/tmp/y.txt")
        assert queue.pending_count() == 2

        queue.dequeue()
        assert queue.pending_count() == 2  # 1 queued + 1 running

    def test_get_job_not_found(self, queue: JobQueue) -> None:
        """get_job for a non-existent id should return None."""
        assert queue.get_job(999) is None


class TestScheduler:
    """Tests for the Scheduler (path normalization + delegation)."""

    def test_normalizes_path(self, scheduler: Scheduler, queue: JobQueue) -> None:
        """Scheduler should normalize relative / tilde paths."""
        job = scheduler.schedule("./some/../file.txt", source="ui")
        # Path should be absolute, no relative segments
        assert not job.file_path.startswith(".")
        assert ".." not in job.file_path

    def test_delegates_to_queue(self, scheduler: Scheduler, queue: JobQueue) -> None:
        """Scheduler should create a job in the underlying queue."""
        scheduler.schedule("/tmp/sched.txt", source="watcher")
        jobs = queue.list_jobs()
        assert len(jobs) == 1
        # Check that the path ends with the expected string to ignore drive letters
        assert jobs[0].file_path.replace("\\", "/").endswith("/tmp/sched.txt")


class TestStateHelpers:
    """Tests for transition_state and should_retry."""

    def test_transition_completed(self, queue: JobQueue) -> None:
        """transition_state to 'completed' should work."""
        queue.enqueue("/tmp/ts.txt")
        job = queue.dequeue()
        done = transition_state(queue, job.id, "completed")
        assert done.status == "completed"

    def test_transition_failed(self, queue: JobQueue) -> None:
        """transition_state to 'failed' should record error."""
        queue.enqueue("/tmp/ts2.txt")
        job = queue.dequeue()
        failed = transition_state(queue, job.id, "failed", error="boom")
        # With attempts < max, it resets to queued (retry)
        assert failed.status == "queued"
        assert failed.error_message == "boom"

    def test_transition_invalid(self, queue: JobQueue) -> None:
        """transition_state to an unknown status should raise."""
        queue.enqueue("/tmp/ts3.txt")
        job = queue.dequeue()
        with pytest.raises(ValueError, match="Unsupported transition"):
            transition_state(queue, job.id, "invalid_status")

    def test_should_retry_true(self) -> None:
        """should_retry is True when attempts < max_attempts."""
        job = Job(
            id=1,
            file_path="x",
            source="ui",
            priority=1,
            status="running",
            attempts=1,
            max_attempts=3,
            error_message=None,
            created_at="",
            updated_at="",
        )
        assert should_retry(job) is True

    def test_should_retry_false(self) -> None:
        """should_retry is False when attempts >= max_attempts."""
        job = Job(
            id=1,
            file_path="x",
            source="ui",
            priority=1,
            status="failed",
            attempts=3,
            max_attempts=3,
            error_message="err",
            created_at="",
            updated_at="",
        )
        assert should_retry(job) is False


class TestWorker:
    """Tests for the async Worker with injected processor."""

    @pytest.fixture
    def mock_ctx(self, queue: JobQueue, tmp_path: Path):
        """Creates a context with a real UnifiedDatabase for get_file_record."""

        class MockContext:
            def __init__(self, q: JobQueue, db: UnifiedDatabase) -> None:
                self._queue = q
                self.db = db

        real_db = UnifiedDatabase(str(tmp_path / "mock_ctx.db"))
        return MockContext(queue, real_db)

    @pytest.mark.asyncio
    async def test_worker_processes_job(self, queue: JobQueue, mock_ctx) -> None:
        """Worker should dequeue a job, call the processor, and complete it."""
        processed: List[str] = []

        def fake_processor(path: str, *args, **kwargs) -> None:
            processed.append(path)

        queue.enqueue("/tmp/work.txt", source="ui")

        worker = Worker(
            queue, processor=fake_processor, poll_interval=0.1, ctx=mock_ctx
        )
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()

        assert processed == ["/tmp/work.txt"]
        job = queue.list_jobs(status="completed")
        assert len(job) == 1

    @pytest.mark.asyncio
    async def test_worker_retries_then_succeeds(
        self, queue: JobQueue, mock_ctx
    ) -> None:
        """Worker should retry a failing job and eventually succeed."""
        call_count = 0

        def flaky_processor(path: str, *args, **kwargs) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")

        queue.enqueue("/tmp/flaky.txt", source="ui")

        worker = Worker(
            queue, processor=flaky_processor, poll_interval=0.1, ctx=mock_ctx
        )
        await worker.start()
        await asyncio.sleep(1.0)
        await worker.stop()

        assert call_count == 2
        final = queue.list_jobs(status="completed")
        assert len(final) == 1

    @pytest.mark.asyncio
    async def test_worker_permanent_failure(self, queue: JobQueue, mock_ctx) -> None:
        """Worker should mark a job as 'failed' after max_attempts."""

        def always_fail(path: str, *args, **kwargs) -> None:
            raise RuntimeError("permanent error")

        queue.enqueue("/tmp/permfail.txt", source="ui")

        worker = Worker(queue, processor=always_fail, poll_interval=0.1, ctx=mock_ctx)
        await worker.start()
        await asyncio.sleep(2.0)
        await worker.stop()

        failed_jobs = queue.list_jobs(status="failed")
        assert len(failed_jobs) == 1
        assert failed_jobs[0].attempts == 3
        # The error message should now correctly contain the processor's error
        assert "permanent error" in failed_jobs[0].error_message
