import hashlib
import logging
import os
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ReindexStrategy(Enum):
    SKIP = "skip"  # No action needed
    FULL_INDEX = "full_index"  # Extract, chunk, and embed
    METADATA_UPDATE = "metadata_update"  # Update path/mtime only
    PURGE = "purge"  # Remove from DB and Vector store


def calculate_file_hash(path: str) -> str:
    """Calculates SHA-256 hash of file content to detect actual changes."""
    sha256_hash = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            # Read in 4KB chunks for memory efficiency
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (FileNotFoundError, PermissionError, OSError) as e:
        logger.error(f"Failed to hash file at {path}: {e}")
        return None


def determine_strategy(
    file_path: str, db_record: Optional[dict], event_type: str = "modified"
) -> ReindexStrategy:
    """
    Determines how to handle a file based on disk state and DB records.
    Now uses event_type to short-circuit logic where possible.
    """
    # 1. Immediate Purge: If the watcher says it's deleted, no need to check disk
    if event_type == "deleted" or not os.path.exists(file_path):
        return ReindexStrategy.PURGE

    # 2. New File: If no DB record exists, we must index it
    if not db_record:
        return ReindexStrategy.FULL_INDEX

    # 3. Quick Check: Compare mtime before expensive hashing
    current_mtime = os.path.getmtime(file_path)
    if current_mtime <= db_record.get("last_modified_timestamp", 0):
        return ReindexStrategy.SKIP

    # 4. Content Check: Only hash if mtime suggests a change
    current_hash = calculate_file_hash(file_path)

    # If hashing failed (e.g. file locked), skip for now to retry later
    if current_hash is None:
        return ReindexStrategy.SKIP

    if current_hash == db_record.get("file_hash"):
        return ReindexStrategy.METADATA_UPDATE

    return ReindexStrategy.FULL_INDEX
