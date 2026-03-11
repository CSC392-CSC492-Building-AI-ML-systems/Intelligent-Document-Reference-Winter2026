"""Unit tests for run_index function with change detection strategies."""

import os
from unittest.mock import Mock, patch

import pytest

from ingestion.change_detector import ReindexStrategy
from ingestion.pipeline import run_index


@pytest.fixture
def mock_db(tmp_path):
    """Mock database for testing."""
    db = Mock()
    return db


@pytest.fixture
def mock_ctx(mock_db):
    """Mock context with database."""
    ctx = Mock()
    ctx.db = mock_db
    ctx.embedder = None
    ctx.embedding_client = None
    ctx.inference_client = None
    ctx.pipeline_config = None
    return ctx


def test_run_index_skip_unchanged_file(tmp_path, mock_ctx):
    """Test that unchanged file is skipped."""
    test_dir = tmp_path / "skip_test"
    test_dir.mkdir()
    f = test_dir / "test.txt"
    f.write_text("content")

    with (
        patch(
            "ingestion.pipeline.determine_strategy", return_value=ReindexStrategy.SKIP
        ),
        patch("ingestion.pipeline.logger") as mock_logger,
    ):
        run_index(str(f), mock_ctx)
        mock_logger.info.assert_called_with(
            "Skipping indexing for %s: no changes detected", str(f)
        )


def test_run_index_full_index_new_file(tmp_path, mock_ctx):
    """Test that new file triggers full indexing."""
    test_dir = tmp_path / "new_file_test"
    test_dir.mkdir()
    f = test_dir / "new.txt"
    f.write_text("new content")

    with (
        patch(
            "ingestion.pipeline.determine_strategy",
            return_value=ReindexStrategy.FULL_INDEX,
        ),
        patch("ingestion.pipeline.run") as mock_run,
    ):
        run_index(str(f), mock_ctx)
        mock_run.assert_called_once()


def test_run_index_purge_deleted_file(tmp_path, mock_ctx):
    """Test that deleted file is purged."""
    test_dir = tmp_path / "purge_test"
    test_dir.mkdir()
    f = test_dir / "deleted.txt"
    # File does not exist

    mock_ctx.db.get_file_record.return_value = {
        "file_hash": "hash",
        "last_modified_timestamp": 123,
    }

    with patch("ingestion.pipeline.logger") as mock_logger:
        run_index(str(f), mock_ctx)
        mock_ctx.db.remove_file.assert_called_with(str(f))
        mock_logger.info.assert_called_with("Purged %s from index", str(f))


def test_run_index_metadata_update(tmp_path, mock_ctx):
    """Test that file with same content but newer mtime updates metadata only."""
    test_dir = tmp_path / "metadata_test"
    test_dir.mkdir()
    f = test_dir / "test.txt"
    f.write_text("content")

    with (
        patch(
            "ingestion.pipeline.determine_strategy",
            return_value=ReindexStrategy.METADATA_UPDATE,
        ),
        patch("ingestion.pipeline.run") as mock_run,
        patch("ingestion.pipeline.logger") as mock_logger,
    ):
        run_index(str(f), mock_ctx)
        # Should not call run() for full indexing
        mock_run.assert_not_called()
        mock_logger.info.assert_called_with("Updated metadata for %s", str(f))
        mock_ctx.db.update_file_metadata.assert_called_with(
            str(f), os.path.getmtime(str(f))
        )


def test_run_index_full_index_changed_content(tmp_path, mock_ctx):
    """Test that file with changed content triggers full indexing."""
    test_dir = tmp_path / "changed_test"
    test_dir.mkdir()
    f = test_dir / "test.txt"
    f.write_text("new content")

    with (
        patch(
            "ingestion.pipeline.determine_strategy",
            return_value=ReindexStrategy.FULL_INDEX,
        ),
        patch("ingestion.pipeline.run") as mock_run,
    ):
        run_index(str(f), mock_ctx)
        mock_run.assert_called_once()


def test_run_index_unsupported_extension(tmp_path, mock_ctx):
    """Test that files with unsupported extensions are ignored."""
    test_dir = tmp_path / "unsupported_test"
    test_dir.mkdir()
    f = test_dir / "test.unsupported"
    f.write_text("content")

    with patch("ingestion.pipeline.run") as mock_run:
        run_index(str(f), mock_ctx)
        mock_run.assert_not_called()


def test_run_index_nonexistent_file(tmp_path, mock_ctx):
    """Test that nonexistent file path returns early."""
    nonexistent = str(tmp_path / "nonexistent.txt")

    mock_ctx.db.get_file_record.return_value = None

    with patch("ingestion.pipeline.run") as mock_run:
        run_index(nonexistent, mock_ctx)
        mock_run.assert_not_called()
