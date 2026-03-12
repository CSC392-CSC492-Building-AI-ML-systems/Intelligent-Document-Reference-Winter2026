"""Filesystem watcher package."""

from watcher.adapters import BaseWatcher, CrossPlatformWatcher, get_watcher
from watcher.core.database import FileRegistry
from watcher.core.scanner import FileScanner
from watcher.service import FileTrackingService

__all__ = [
    "BaseWatcher",
    "CrossPlatformWatcher",
    "FileRegistry",
    "FileScanner",
    "FileTrackingService",
    "get_watcher",
]
