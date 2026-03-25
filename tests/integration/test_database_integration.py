"""Integration tests for the UnifiedDatabase module."""

import uuid
from pathlib import Path
from typing import Generator, List

import pytest

from db import UnifiedDatabase


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Provide a temporary database path.

    Args:
        tmp_path: Pytest's temporary directory fixture.

    Returns:
        String path to the temporary database file.
    """
    return str(tmp_path / "test_unified_integration.db")


@pytest.fixture
def db(db_path: str) -> Generator[UnifiedDatabase, None, None]:
    """Provide an initialized UnifiedDatabase instance.

    Args:
        db_path: Path to the database file.

    Yields:
        Initialized UnifiedDatabase instance.
    """
    database = UnifiedDatabase(db_path)
    yield database


@pytest.fixture
def fake_vector() -> List[float]:
    """Provide a consistent fake vector for testing.

    Returns:
        List of 3072 float values for testing vector operations.
    """
    return [0.1] * 3072


def test_simple_integration(db: UnifiedDatabase, fake_vector: List[float]) -> None:
    """Run a simple integration test for the UnifiedDatabase module.

    This test:
    1. Registers a file.
    2. Creates a version.
    3. Adds a document chunk and its vector.
    4. Searches for the vector and verifies the result.

    Args:
        db: UnifiedDatabase instance fixture.
        fake_vector: Test vector fixture.
    """
    file_id = db.register_file("docs/intro.txt", "hash123", 3072, 0.0)

    version_id = db.create_version(file_id, "v1_hash")

    chunk_id = str(uuid.uuid4())

    chunks = [
        {
            "id": chunk_id,
            "chunk_index": 0,
            "start_offset": 0,
            "end_offset": 100,
            "text_content": "Hello world this is a test chunk.",
        }
    ]

    db.add_document(file_id, version_id, chunks, [fake_vector])

    results = db.search(fake_vector, limit=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == chunk_id
    assert results[0]["text_content"] == "Hello world this is a test chunk."


def test_get_file_record_retrieval(db: UnifiedDatabase):
    """Verifies that get_file_record returns correct metadata for change detection."""
    test_path = "docs/test.txt"
    test_hash = "abc123hash"
    test_mtime = 123456789.0

    # 1. Register a new file
    db.register_file(test_path, test_hash, 1024, test_mtime)

    # 2. Retrieve the record
    record = db.get_file_record(test_path)

    # 3. Assertions
    assert record is not None
    assert record["file_hash"] == test_hash
    assert record["last_modified_timestamp"] == test_mtime

    # 4. Verify non-existent file returns None
    assert db.get_file_record("non_existent.txt") is None


def test_remove_file(db: UnifiedDatabase, fake_vector: List[float]):
    """Verifies that remove_file deletes the file and associated data."""
    test_path = "docs/remove_test.txt"
    test_hash = "remove_hash"
    test_mtime = 123456789.0

    # 1. Register and add content
    file_id = db.register_file(test_path, test_hash, 1024, test_mtime)
    version_id = db.create_version(file_id, "v1")
    chunk_id = str(uuid.uuid4())
    chunks = [
        {
            "id": chunk_id,
            "chunk_index": 0,
            "start_offset": 0,
            "end_offset": 10,
            "text_content": "test",
        }
    ]
    db.add_document(file_id, version_id, chunks, [fake_vector])

    # 2. Verify data exists
    record = db.get_file_record(test_path)
    assert record is not None
    results = db.search(fake_vector, limit=1)
    assert len(results) == 1

    # 3. Remove file
    db.remove_file(test_path)

    # 4. Verify data is gone
    assert db.get_file_record(test_path) is None
    results_after = db.search(fake_vector, limit=1)
    assert len(results_after) == 0


def test_update_file_metadata(db: UnifiedDatabase):
    """Verifies that update_file_metadata updates only the timestamp."""
    test_path = "docs/update_test.txt"
    original_mtime = 123456789.0
    new_mtime = 987654321.0

    # 1. Register file
    db.register_file(test_path, "hash", 1024, original_mtime)

    # 2. Update metadata
    db.update_file_metadata(test_path, new_mtime)

    # 3. Verify only timestamp changed
    record = db.get_file_record(test_path)
    assert record is not None
    assert record["file_hash"] == "hash"  # Unchanged
    assert record["last_modified_timestamp"] == new_mtime  # Updated
