"""Unit tests for the watcher subsystem (FileRegistry, FileTrackingService)."""

from pathlib import Path
from typing import Dict, Generator, List
from unittest.mock import MagicMock, patch

import pytest

from watcher import FileRegistry, FileScanner, FileTrackingService


@pytest.fixture
def registry_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_registry.db")


@pytest.fixture
def registry(registry_path: str) -> Generator[FileRegistry, None, None]:
    yield FileRegistry(db_path=registry_path)


class TestFileRegistry:
    """Tests for the watcher's file registry database."""

    def test_upsert_and_get_file_state(self, registry: FileRegistry) -> None:
        registry.upsert_file("/tmp/a.txt", 1000.0)
        state = registry.get_file_state("/tmp/a.txt")
        assert state is not None
        assert state["path"] == "/tmp/a.txt"
        assert state["last_modified"] == 1000.0

    def test_upsert_updates_existing(self, registry: FileRegistry) -> None:
        registry.upsert_file("/tmp/a.txt", 1000.0)
        registry.upsert_file("/tmp/a.txt", 2000.0)
        state = registry.get_file_state("/tmp/a.txt")
        assert state["last_modified"] == 2000.0

    def test_get_file_state_not_found(self, registry: FileRegistry) -> None:
        assert registry.get_file_state("/nonexistent") is None

    def test_remove_file(self, registry: FileRegistry) -> None:
        registry.upsert_file("/tmp/rm.txt", 1000.0)
        registry.remove_file("/tmp/rm.txt")
        assert registry.get_file_state("/tmp/rm.txt") is None

    def test_add_and_get_watch_paths(self, registry: FileRegistry) -> None:
        registry.add_watch_path("/watch/dir1", ["/watch/dir1/.git"])
        paths = registry.get_watch_paths()
        assert len(paths) == 1
        assert paths[0]["path"] == "/watch/dir1"
        assert paths[0]["excluded_files"] == ["/watch/dir1/.git"]

    def test_add_watch_path_upserts(self, registry: FileRegistry) -> None:
        registry.add_watch_path("/watch/dir1", [])
        registry.add_watch_path("/watch/dir1", ["/watch/dir1/.env"])
        paths = registry.get_watch_paths()
        assert len(paths) == 1
        assert paths[0]["excluded_files"] == ["/watch/dir1/.env"]

    def test_remove_watch_path(self, registry: FileRegistry) -> None:
        registry.add_watch_path("/watch/dir1")
        registry.remove_watch_path("/watch/dir1")
        paths = registry.get_watch_paths()
        assert len(paths) == 0

    def test_remove_watch_path_by_id(self, registry: FileRegistry) -> None:
        registry.add_watch_path("/watch/dir1")
        paths = registry.get_watch_paths()
        registry.remove_watch_path_by_id(paths[0]["id"])
        assert len(registry.get_watch_paths()) == 0


class _StubWatcher:
    """Minimal watcher stub that records schedule/unschedule calls."""

    def __init__(self) -> None:
        self.scheduled: Dict[str, List[str]] = {}
        self.started = False

    def start(self, paths: List[str]) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def schedule_watch(self, path: str, excluded_files: List[str]) -> None:
        self.scheduled[path] = excluded_files

    def unschedule_watch(self, path: str) -> None:
        self.scheduled.pop(path, None)

    def get_watched_paths(self) -> List[str]:
        return list(self.scheduled.keys())


class TestFileTrackingService:
    """Tests for the FileTrackingService with injected dependencies."""

    def test_handle_event_schedules_job(self, registry: FileRegistry) -> None:
        scheduler = MagicMock()
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )
        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1234.0)),
        ):
            service.handle_event("/tmp/new.txt", "created")

        scheduler.schedule.assert_called_once_with("/tmp/new.txt", source="watcher")

    def test_handle_deleted_event(self, registry: FileRegistry) -> None:
        registry.upsert_file("/tmp/gone.txt", 1000.0)
        scheduler = MagicMock()
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        service.handle_event("/tmp/gone.txt", "deleted")

        assert registry.get_file_state("/tmp/gone.txt") is None
        scheduler.schedule.assert_called_once_with("/tmp/gone.txt", source="watcher")

    def test_handle_moved_event(self, registry: FileRegistry) -> None:
        registry.upsert_file("/tmp/old.txt", 1000.0)
        scheduler = MagicMock()
        service = FileTrackingService(
            registry=registry, scheduler=scheduler, watcher=_StubWatcher()
        )

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=2000.0)),
        ):
            service.handle_event("/tmp/old.txt", "moved", dest_path="/tmp/new.txt")

        assert registry.get_file_state("/tmp/old.txt") is None
        assert registry.get_file_state("/tmp/new.txt") is not None
        assert scheduler.schedule.call_count == 1
        scheduler.schedule.assert_called_with("/tmp/new.txt", source="watcher")

    def test_no_scheduler_skips_silently(self, registry: FileRegistry) -> None:
        service = FileTrackingService(
            registry=registry, scheduler=None, watcher=_StubWatcher()
        )
        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1234.0)),
        ):
            service.handle_event("/tmp/ok.txt", "modified")

    def test_start_background_and_stop(self, registry: FileRegistry) -> None:
        stub = _StubWatcher()
        service = FileTrackingService(
            registry=registry, scheduler=MagicMock(), watcher=stub
        )

        service.start_background()
        assert stub.started
        assert service._running
        assert service._sync_thread is not None
        assert service._sync_thread.is_alive()

        service.stop()
        assert not service._running
        assert not stub.started

    def test_reconcile_adds_missing_paths(self, registry: FileRegistry) -> None:
        registry.add_watch_path("/watch/new")
        stub = _StubWatcher()
        service = FileTrackingService(
            registry=registry, scheduler=MagicMock(), watcher=stub
        )

        service._reconcile()

        assert "/watch/new" in stub.scheduled

    def test_reconcile_removes_extra_paths(self, registry: FileRegistry) -> None:
        stub = _StubWatcher()
        stub.scheduled["/watch/stale"] = []
        service = FileTrackingService(
            registry=registry, scheduler=MagicMock(), watcher=stub
        )

        service._reconcile()

        assert "/watch/stale" not in stub.scheduled


class TestFileScanner:
    """Tests for the filesystem scanner."""

    def test_scan_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("world")

        scanner = FileScanner([])
        results = list(scanner.scan_directory(str(tmp_path)))
        paths = [info["path"] for _, info in results]

        assert str(tmp_path / "a.txt") in paths
        assert str(sub / "b.txt") in paths

    def test_scan_excludes_files(self, tmp_path: Path) -> None:
        (tmp_path / "keep.txt").write_text("yes")
        (tmp_path / "skip.txt").write_text("no")

        scanner = FileScanner([])
        results = list(
            scanner.scan_directory(
                str(tmp_path), excluded_files=[str(tmp_path / "skip.txt")]
            )
        )
        paths = [info["path"] for _, info in results]

        assert str(tmp_path / "keep.txt") in paths
        assert str(tmp_path / "skip.txt") not in paths

    def test_calculate_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "hashme.txt"
        f.write_text("deterministic")
        scanner = FileScanner([])
        h1 = scanner.calculate_hash(str(f))
        h2 = scanner.calculate_hash(str(f))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex
