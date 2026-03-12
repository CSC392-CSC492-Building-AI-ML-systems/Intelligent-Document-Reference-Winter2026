import os
from unittest.mock import patch

from ingestion.change_detector import ReindexStrategy, determine_strategy


def test_new_file_strategy(tmp_path):
    """Verify that a file not in DB triggers a full index."""
    # Create a unique sub-directory for this specific test case
    test_dir = tmp_path / "change_detector_test"
    test_dir.mkdir()

    f = test_dir / "some_new_file.txt"
    f.write_text("new file content")

    # Now that the file exists in an isolated path, it bypasses the PURGE check
    assert determine_strategy(str(f), None) == ReindexStrategy.FULL_INDEX


def test_identical_file_strategy(tmp_path):
    """Verify that identical content returns SKIP or METADATA_UPDATE."""
    # Create a unique sub-directory to avoid any shared state
    test_dir = tmp_path / "identical_test"
    test_dir.mkdir()

    f = test_dir / "test.txt"
    f.write_text("content")

    # Mock DB record with same hash and future timestamp
    db_record = {
        "file_hash": "ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73",
        "last_modified_timestamp": os.path.getmtime(f)
        + 10,  # Future mtime to trigger SKIP
    }

    # If mtime is newer in DB, it should SKIP regardless of content
    assert determine_strategy(str(f), db_record) == ReindexStrategy.SKIP


def test_metadata_update_strategy(tmp_path):
    """Verify that file with same content but newer mtime triggers METADATA_UPDATE."""
    test_dir = tmp_path / "metadata_test"
    test_dir.mkdir()

    f = test_dir / "test.txt"
    f.write_text("content")

    # Mock DB record with same hash but older timestamp
    db_record = {
        "file_hash": "ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73",
        "last_modified_timestamp": os.path.getmtime(f) - 10,  # Older mtime
    }

    assert determine_strategy(str(f), db_record) == ReindexStrategy.METADATA_UPDATE


def test_full_index_strategy(tmp_path):
    """Verify that file with changed content triggers FULL_INDEX."""
    test_dir = tmp_path / "full_index_test"
    test_dir.mkdir()

    f = test_dir / "test.txt"
    f.write_text("content")

    # Mock DB record with different hash
    db_record = {
        "file_hash": "different_hash",
        "last_modified_timestamp": os.path.getmtime(f) - 10,
    }

    assert determine_strategy(str(f), db_record) == ReindexStrategy.FULL_INDEX


def test_purge_deleted_file(tmp_path):
    """Verify that deleted file triggers PURGE."""
    test_dir = tmp_path / "purge_test"
    test_dir.mkdir()

    f = test_dir / "deleted_file.txt"
    # File does not exist

    db_record = {
        "file_hash": "some_hash",
        "last_modified_timestamp": 1234567890,
    }

    assert determine_strategy(str(f), db_record) == ReindexStrategy.PURGE


def test_purge_event_type_deleted(tmp_path):
    """Verify that event_type 'deleted' triggers PURGE even if file exists."""
    test_dir = tmp_path / "purge_event_test"
    test_dir.mkdir()

    f = test_dir / "existing_file.txt"
    f.write_text("content")

    db_record = {
        "file_hash": "some_hash",
        "last_modified_timestamp": 1234567890,
    }

    assert determine_strategy(str(f), db_record, "deleted") == ReindexStrategy.PURGE


def test_skip_with_older_mtime(tmp_path):
    """Verify SKIP when DB mtime is newer or equal."""
    test_dir = tmp_path / "skip_test"
    test_dir.mkdir()

    f = test_dir / "test.txt"
    f.write_text("content")

    current_mtime = os.path.getmtime(f)
    db_record = {
        "file_hash": "ed7002b479e9ac567e5029a696a744e66bdc3a272051214c519faef045505102",
        "last_modified_timestamp": current_mtime,  # Same mtime
    }

    assert determine_strategy(str(f), db_record) == ReindexStrategy.SKIP


def test_hash_failure_returns_skip(tmp_path):
    """Verify that if hashing fails, it returns SKIP."""
    test_dir = tmp_path / "hash_fail_test"
    test_dir.mkdir()

    f = test_dir / "test.txt"
    f.write_text("content")

    # Mock DB record with different hash to force hashing
    db_record = {
        "file_hash": "different",
        "last_modified_timestamp": os.path.getmtime(f) - 10,
    }

    # Mock calculate_file_hash to return None (failure)
    with patch("ingestion.change_detector.calculate_file_hash", return_value=None):
        strategy = determine_strategy(str(f), db_record)
        assert strategy == ReindexStrategy.SKIP
