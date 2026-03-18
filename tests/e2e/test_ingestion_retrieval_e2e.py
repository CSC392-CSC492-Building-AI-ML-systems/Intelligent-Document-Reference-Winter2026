"""End-to-end tests for the full ingestion → retrieval pipeline.

Covers: file indexing, file status tracking, re-add after removal,
small/empty files, selected-file filtering, and empty selection semantics.

All tests use temporary databases and mocked embedding/inference clients
so no real API keys or network calls are needed.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Generator, List

import pytest

from db.unified import UnifiedDatabase
from inference.responder import Responder
from inference.retriever import Retriever
from jobs.queue import JobQueue
from jobs.scheduler import Scheduler
from watcher.core.database import FileRegistry

# ── Fixtures ─────────────────────────────────────────────────────────────────

EMBED_DIM = 3072
FAKE_VECTOR = [0.1] * EMBED_DIM


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def unified_db(tmp_path: Path) -> Generator[UnifiedDatabase, None, None]:
    yield UnifiedDatabase(db_path=str(tmp_path / "test_e2e.db"))


@pytest.fixture
def registry(tmp_path: Path) -> Generator[FileRegistry, None, None]:
    yield FileRegistry(db_path=str(tmp_path / "watcher_e2e.db"))


@pytest.fixture
def job_queue(tmp_path: Path) -> Generator[JobQueue, None, None]:
    yield JobQueue(db_path=str(tmp_path / "jobs_e2e.db"))


@pytest.fixture
def scheduler(job_queue: JobQueue) -> Scheduler:
    return Scheduler(job_queue)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _add_file_to_db(
    db: UnifiedDatabase,
    path: str,
    content: str,
    vector: List[float] | None = None,
    mark_indexed: bool = True,
) -> int:
    """Register a file, add a single chunk+vector, optionally mark indexed."""
    h = _hash(content)
    file_id = db.register_file(path, h, len(content), 1000.0)
    version_id = db.create_version(file_id, h)
    vec = vector or FAKE_VECTOR
    chunks = [
        {
            "id": str(uuid.uuid4()),
            "chunk_index": 0,
            "start_offset": 0,
            "end_offset": len(content),
            "text_content": content,
        },
    ]
    db.add_document(file_id, version_id, chunks, [vec])
    if mark_indexed:
        db.mark_file_indexed(file_id)
    return file_id


class FakeEmbeddingClient:
    """Deterministic embedder that returns the same vector for any text."""

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        return [FAKE_VECTOR for _ in texts]


class FakeInferenceClient:
    """Returns a predictable answer."""

    def generate(self, prompt: str, **kwargs) -> str:
        return "This is a test answer based on retrieved context."


# ── Test: Full indexing → retrieval ─────────────────────────────────────────


class TestFullIndexingRetrieval:
    """Index files into the DB and verify retrieval returns them."""

    def test_index_then_search(self, unified_db: UnifiedDatabase) -> None:
        """A file stored in the DB is found via vector search."""
        _add_file_to_db(
            unified_db,
            "/docs/guide.md",
            "Python was created by Guido van Rossum in 1991.",
        )
        results = unified_db.search_with_metadata(FAKE_VECTOR, limit=5)
        assert len(results) == 1
        assert "Guido" in results[0]["text_content"]
        assert results[0]["file_path"] == "/docs/guide.md"

    def test_multiple_files_returned(self, unified_db: UnifiedDatabase) -> None:
        """Multiple indexed files appear in search results."""
        _add_file_to_db(unified_db, "/docs/a.md", "Content of file A.")
        _add_file_to_db(unified_db, "/docs/b.md", "Content of file B.")

        results = unified_db.search_with_metadata(FAKE_VECTOR, limit=10)
        paths = {r["file_path"] for r in results}
        assert "/docs/a.md" in paths
        assert "/docs/b.md" in paths

    @pytest.mark.asyncio
    async def test_responder_end_to_end(self, unified_db: UnifiedDatabase) -> None:
        """Full pipeline: query → embed → retrieve → generate → citations."""
        _add_file_to_db(
            unified_db,
            "/docs/guide.md",
            "The capital of France is Paris.",
        )

        responder = Responder(
            db=unified_db,
            embedding_client=FakeEmbeddingClient(),
            inference_client=FakeInferenceClient(),
        )
        result = await responder.respond("What is the capital of France?")
        assert "answer" in result
        assert "citations" in result
        assert "chunks" in result
        assert len(result["chunks"]) >= 1


# ── Test: File status tracking ──────────────────────────────────────────────


class TestFileStatusTracking:
    """Verify file status transitions: pending → indexed."""

    def test_new_file_is_pending(self, unified_db: UnifiedDatabase) -> None:
        """Newly registered file starts with status='pending'."""
        unified_db.register_file("/test/new.txt", "hash1", 100, 1000.0)
        statuses = unified_db.get_all_file_statuses()
        assert statuses["/test/new.txt"] == "pending"

    def test_mark_indexed(self, unified_db: UnifiedDatabase) -> None:
        """mark_file_indexed sets status to 'indexed'."""
        file_id = unified_db.register_file("/test/done.txt", "hash2", 100, 1000.0)
        unified_db.mark_file_indexed(file_id)
        statuses = unified_db.get_all_file_statuses()
        assert statuses["/test/done.txt"] == "indexed"

    def test_hash_change_sets_outdated(self, unified_db: UnifiedDatabase) -> None:
        """Re-registering with a different hash sets status to 'outdated'."""
        file_id = unified_db.register_file("/test/changed.txt", "hash_v1", 100, 1000.0)
        unified_db.mark_file_indexed(file_id)
        assert unified_db.get_all_file_statuses()["/test/changed.txt"] == "indexed"

        # Re-register with different hash
        unified_db.register_file("/test/changed.txt", "hash_v2", 200, 2000.0)
        assert unified_db.get_all_file_statuses()["/test/changed.txt"] == "outdated"

    def test_mark_indexed_is_idempotent(self, unified_db: UnifiedDatabase) -> None:
        """Calling mark_file_indexed twice doesn't raise or change state."""
        file_id = unified_db.register_file("/test/idem.txt", "hash3", 100, 1000.0)
        unified_db.mark_file_indexed(file_id)
        unified_db.mark_file_indexed(file_id)
        assert unified_db.get_all_file_statuses()["/test/idem.txt"] == "indexed"


# ── Test: File removal ──────────────────────────────────────────────────────


class TestFileRemoval:
    """Removing a file purges its data from the database."""

    def test_remove_single_file(self, unified_db: UnifiedDatabase) -> None:
        """remove_file deletes file, chunks, and vectors."""
        _add_file_to_db(unified_db, "/docs/remove_me.md", "Some text to remove.")
        assert unified_db.get_file_record("/docs/remove_me.md") is not None

        unified_db.remove_file("/docs/remove_me.md")

        assert unified_db.get_file_record("/docs/remove_me.md") is None
        results = unified_db.search_with_metadata(FAKE_VECTOR, limit=5)
        assert len(results) == 0

    def test_remove_directory(self, unified_db: UnifiedDatabase) -> None:
        """remove_files_under_directory purges all files under a prefix."""
        _add_file_to_db(unified_db, "/project/src/a.py", "File A content.")
        _add_file_to_db(unified_db, "/project/src/b.py", "File B content.")
        _add_file_to_db(unified_db, "/other/c.py", "File C content.")

        removed = unified_db.remove_files_under_directory("/project/src")

        assert removed == 2
        assert unified_db.get_file_record("/project/src/a.py") is None
        assert unified_db.get_file_record("/project/src/b.py") is None
        # File outside the directory is preserved
        assert unified_db.get_file_record("/other/c.py") is not None


# ── Test: Re-add after removal (Issue #1 regression) ───────────────────────


class TestReAddAfterRemoval:
    """Re-adding a file/path after removal should schedule new indexing."""

    def test_readd_single_file_via_registry(self, registry: FileRegistry) -> None:
        """add_watch_path re-activates a previously deactivated entry."""
        registry.add_watch_path("/docs/readme.md", [])
        paths_before = registry.get_watch_paths()
        assert any(p["path"] == "/docs/readme.md" for p in paths_before)

        # Remove (deactivate)
        registry.remove_watch_path("/docs/readme.md")
        paths_after_removal = registry.get_watch_paths()
        assert not any(p["path"] == "/docs/readme.md" for p in paths_after_removal)

        # Re-add (should re-activate)
        registry.add_watch_path("/docs/readme.md", [])
        paths_after_readd = registry.get_watch_paths()
        assert any(p["path"] == "/docs/readme.md" for p in paths_after_readd)

    def test_readd_is_not_in_active_paths_after_removal(
        self, registry: FileRegistry
    ) -> None:
        """After removal, get_watch_paths (active only) excludes the path."""
        registry.add_watch_path("/docs/file.txt", [])
        registry.remove_watch_path("/docs/file.txt")

        active = {d["path"] for d in registry.get_watch_paths()}
        all_paths = set(registry.get_all_monitor_paths())

        # Active should NOT contain it; all_paths SHOULD (it's inactive, not deleted)
        assert "/docs/file.txt" not in active
        assert "/docs/file.txt" in all_paths

    def test_job_queue_replaces_completed_job(self, job_queue: JobQueue) -> None:
        """Enqueuing a file that previously completed creates a fresh queued job."""
        job = job_queue.enqueue("/docs/readme.md", source="ui")
        job_queue.dequeue()  # running
        job_queue.complete(job.id)

        # Re-enqueue
        new_job = job_queue.enqueue("/docs/readme.md", source="ui")
        assert new_job.status == "queued"
        assert new_job.attempts == 0

    def test_scheduler_schedules_readded_file(
        self, scheduler: Scheduler, job_queue: JobQueue
    ) -> None:
        """Scheduler creates a job for a re-added file path."""
        scheduler.schedule("/docs/first_time.py", source="ui")
        jobs = job_queue.list_jobs()
        assert len(jobs) == 1

        # Complete the first job
        j = job_queue.dequeue()
        job_queue.complete(j.id)

        # Re-schedule — should create a new queued job
        scheduler.schedule("/docs/first_time.py", source="ui")
        pending = job_queue.list_jobs(status="queued")
        assert len(pending) == 1


# ── Test: Small / empty files (Issue #2a) ──────────────────────────────────


class TestSmallFileHandling:
    """Small files should be marked indexed even with no storable chunks."""

    def test_register_and_mark_no_chunks(self, unified_db: UnifiedDatabase) -> None:
        """A file with no chunks can still be registered and marked indexed."""
        file_id = unified_db.register_file("/docs/tiny.txt", "hash_tiny", 5, 1000.0)
        # No chunks added — simulate _register_and_mark_indexed behaviour
        unified_db.mark_file_indexed(file_id)

        statuses = unified_db.get_all_file_statuses()
        assert statuses["/docs/tiny.txt"] == "indexed"

    def test_empty_file_does_not_appear_in_search(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """A file marked indexed with no chunks returns nothing from search."""
        file_id = unified_db.register_file("/docs/empty.txt", "hash_empty", 0, 1000.0)
        unified_db.mark_file_indexed(file_id)

        results = unified_db.search_with_metadata(FAKE_VECTOR, limit=5)
        assert len(results) == 0


# ── Test: Selected-file filtering (Issue #2c) ──────────────────────────────


class TestSelectedFileFiltering:
    """Verify that file_ids filtering restricts search results."""

    def test_filter_by_file_ids(self, unified_db: UnifiedDatabase) -> None:
        """search_with_metadata respects file_ids filter."""
        id_a = _add_file_to_db(unified_db, "/docs/a.md", "Content A.")
        _add_file_to_db(unified_db, "/docs/b.md", "Content B.")

        # Search restricted to file A only
        results = unified_db.search_with_metadata(
            FAKE_VECTOR, limit=10, file_ids=[id_a]
        )
        paths = {r["file_path"] for r in results}
        assert paths == {"/docs/a.md"}

    def test_get_file_ids_for_paths(self, unified_db: UnifiedDatabase) -> None:
        """get_file_ids_for_paths returns correct IDs for given paths."""
        id_a = _add_file_to_db(unified_db, "/docs/a.md", "A.")
        id_b = _add_file_to_db(unified_db, "/docs/b.md", "B.")
        _add_file_to_db(unified_db, "/other/c.md", "C.")

        ids = unified_db.get_file_ids_for_paths(["/docs/a.md", "/docs/b.md"])
        assert set(ids) == {id_a, id_b}

    def test_get_file_ids_for_nonexistent_path(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """get_file_ids_for_paths returns empty list for unknown paths."""
        ids = unified_db.get_file_ids_for_paths(["/nope/missing.txt"])
        assert ids == []

    def test_get_file_ids_empty_input(self, unified_db: UnifiedDatabase) -> None:
        """get_file_ids_for_paths with empty list returns empty list."""
        ids = unified_db.get_file_ids_for_paths([])
        assert ids == []


# ── Test: Empty selection semantics (Issue #2c) ────────────────────────────


class TestEmptySelectionSemantics:
    """When user deselects all files, queries should return no results."""

    @pytest.mark.asyncio
    async def test_retriever_empty_file_ids_returns_empty(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """Retriever returns [] when file_ids is an explicit empty list."""
        _add_file_to_db(unified_db, "/docs/a.md", "Some content.")

        retriever = Retriever(
            db=unified_db,
            embedding_client=FakeEmbeddingClient(),
        )
        results = await retriever.retrieve("query", file_ids=[])
        assert results == []

    @pytest.mark.asyncio
    async def test_retriever_none_file_ids_searches_everything(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """Retriever with file_ids=None returns all matching chunks."""
        _add_file_to_db(unified_db, "/docs/a.md", "Some content.")

        retriever = Retriever(
            db=unified_db,
            embedding_client=FakeEmbeddingClient(),
        )
        results = await retriever.retrieve("query", file_ids=None)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_responder_empty_selected_files(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """Responder with selected_files=[] returns 'no relevant documents'."""
        _add_file_to_db(unified_db, "/docs/a.md", "Some content here.")

        responder = Responder(
            db=unified_db,
            embedding_client=FakeEmbeddingClient(),
            inference_client=FakeInferenceClient(),
        )
        result = await responder.respond("test query", selected_files=[])
        assert result["citations"] == []
        assert "couldn't find" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_responder_none_selected_files_searches_all(
        self, unified_db: UnifiedDatabase
    ) -> None:
        """Responder with selected_files=None searches everything."""
        _add_file_to_db(unified_db, "/docs/a.md", "Some content.")

        responder = Responder(
            db=unified_db,
            embedding_client=FakeEmbeddingClient(),
            inference_client=FakeInferenceClient(),
        )
        result = await responder.respond("test query", selected_files=None)
        assert len(result["chunks"]) >= 1


# ── Test: Watcher + Jobs integration ────────────────────────────────────────


class TestWatcherJobsIntegration:
    """End-to-end: registry changes propagate to the job queue."""

    def test_add_remove_readd_creates_jobs(
        self,
        registry: FileRegistry,
        scheduler: Scheduler,
        job_queue: JobQueue,
    ) -> None:
        """Full lifecycle: add → index → remove → re-add triggers new job."""
        # 1. Add and schedule
        registry.add_watch_path("/docs/lifecycle.md", [])
        registry.upsert_file("/docs/lifecycle.md", 100.0)
        scheduler.schedule("/docs/lifecycle.md", source="ui")

        # 2. Process (dequeue + complete)
        job = job_queue.dequeue()
        assert job is not None
        job_queue.complete(job.id)

        # 3. Remove
        registry.remove_watch_path("/docs/lifecycle.md")
        active = {d["path"] for d in registry.get_watch_paths()}
        assert "/docs/lifecycle.md" not in active

        # 4. Re-add and re-schedule
        registry.add_watch_path("/docs/lifecycle.md", [])
        registry.upsert_file("/docs/lifecycle.md", 200.0)
        scheduler.schedule("/docs/lifecycle.md", source="ui")

        # Should have a new queued job
        pending = job_queue.list_jobs(status="queued")
        assert len(pending) == 1
        assert Path(pending[0].file_path) == Path("/docs/lifecycle.md").absolute()

    def test_scan_filters_unsupported_extensions(
        self,
        tmp_path: Path,
        registry: FileRegistry,
        scheduler: Scheduler,
        job_queue: JobQueue,
    ) -> None:
        """Only files with supported extensions get scheduled."""
        (tmp_path / "good.py").write_text("print('hello')")
        (tmp_path / "bad.xyz123").write_text("unsupported")

        # Manually schedule only .py files (simulates pipeline filtering)
        for f in tmp_path.iterdir():
            if f.suffix.lower() == ".py":
                scheduler.schedule(str(f), source="ui")

        jobs = job_queue.list_jobs()
        paths = [j.file_path for j in jobs]
        assert any("good.py" in p for p in paths)
        assert not any("bad.xyz123" in p for p in paths)
