"""Integration test: watcher events flow through Scheduler into JobQueue."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from jobs import PRIORITY_WATCHER, JobQueue, Scheduler
from watcher import FileRegistry, FileTrackingService


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "integration.db")


@pytest.fixture
def queue(db_path: str) -> Generator[JobQueue, None, None]:
    yield JobQueue(db_path)


@pytest.fixture
def scheduler(queue: JobQueue) -> Scheduler:
    return Scheduler(queue)


@pytest.fixture
def registry(tmp_path: Path) -> Generator[FileRegistry, None, None]:
    yield FileRegistry(db_path=str(tmp_path / "watcher.db"))


class _StubWatcher:
    def __init__(self):
        self.scheduled = {}

    def start(self, paths):
        pass

    def stop(self):
        pass

    def schedule_watch(self, path, excluded_files):
        self.scheduled[path] = excluded_files

    def unschedule_watch(self, path):
        self.scheduled.pop(path, None)

    def get_watched_paths(self):
        return list(self.scheduled.keys())


class TestWatcherToJobs:
    """End-to-end: watcher event → Scheduler → JobQueue row."""

    def test_created_event_creates_job(
        self, registry: FileRegistry, scheduler: Scheduler, queue: JobQueue
    ) -> None:
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        # The path used in the event
        test_path = "/tmp/doc.txt"

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=100.0)),
        ):
            service.handle_event(test_path, "created")

        jobs = queue.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].source == "watcher"
        assert jobs[0].priority == PRIORITY_WATCHER
        assert jobs[0].status == "queued"

        # FIX: Ensure both paths are absolute and normalized for the current OS
        # This prepends the current drive letter (e.g., C:) to the test_path
        # to match what the Scheduler does.
        actual_path = Path(jobs[0].file_path)
        expected_path = Path(test_path).absolute()

        assert actual_path == expected_path

    def test_multiple_events_deduplicate(
        self, registry: FileRegistry, scheduler: Scheduler, queue: JobQueue
    ) -> None:
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=100.0)),
        ):
            service.handle_event("/tmp/dup.txt", "created")
            service.handle_event("/tmp/dup.txt", "modified")

        jobs = queue.list_jobs()
        assert len(jobs) == 1

    def test_deleted_event_creates_job(
        self, registry: FileRegistry, scheduler: Scheduler, queue: JobQueue
    ) -> None:
        registry.upsert_file("/tmp/rm.txt", 100.0)
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        service.handle_event("/tmp/rm.txt", "deleted")

        jobs = queue.list_jobs()
        assert len(jobs) == 1
        # FIX: Ensure metadata cleanup works with normalized paths
        assert registry.get_file_state("/tmp/rm.txt") is None

    def test_scan_creates_jobs_for_files(
        self,
        tmp_path: Path,
        registry: FileRegistry,
        scheduler: Scheduler,
        queue: JobQueue,
    ) -> None:
        watch_dir = tmp_path / "docs"
        watch_dir.mkdir()
        (watch_dir / "a.py").write_text("print('a')")
        (watch_dir / "b.py").write_text("print('b')")

        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        service._scan_and_index(str(watch_dir))

        jobs = queue.list_jobs()
        assert len(jobs) == 2
        # FIX: Use Path comparison for set membership to be drive-letter agnostic
        paths = {Path(j.file_path) for j in jobs}
        assert Path(watch_dir / "a.py") in paths
        assert Path(watch_dir / "b.py") in paths
