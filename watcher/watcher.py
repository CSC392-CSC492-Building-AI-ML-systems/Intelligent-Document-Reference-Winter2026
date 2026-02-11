"""Filesystem watcher using watchdog library.

Monitors filesystem changes and enqueues indexing jobs.
"""
import logging
import time
from pathlib import Path
from typing import Optional, List, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from watcher.events import FileEvent
from watcher.debounce import DebounceHandler
from jobs.scheduler import schedule_index_job, schedule_delete_job


logger = logging.getLogger(__name__)


class DocumentWatcherHandler(FileSystemEventHandler):
    """Handler for file system events that schedules indexing jobs."""
    
    def __init__(self, ctx: Optional[Any] = None, debounce_delay: float = 2.0):
        """
        Initialize watcher handler.
        
        Args:
            ctx: Application context
            debounce_delay: Delay in seconds before processing events
        """
        super().__init__()
        self.ctx = ctx
        self._debouncer = DebounceHandler(debounce_delay, self._process_event)
        self._supported_extensions = {'.txt', '.md', '.pdf', '.docx', '.html', '.json', '.csv'}
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        self._debouncer.add_event(FileEvent(event.src_path, "created"))
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if event.is_directory:
            return
        
        self._debouncer.add_event(FileEvent(event.src_path, "modified"))
    
    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if event.is_directory:
            return
        
        self._debouncer.add_event(FileEvent(event.src_path, "deleted"))
    
    def _process_event(self, event: FileEvent):
        """Process a debounced file event."""
        path = Path(event.path)
        
        # Filter by file extension
        if path.suffix.lower() not in self._supported_extensions:
            logger.debug(f"Skipping unsupported file type: {path}")
            return
        
        logger.info(f"Processing {event.type} event for: {path}")
        
        # Schedule appropriate job
        if event.type in ("created", "modified"):
            job_id = schedule_index_job(str(path), priority=2)
            if job_id:
                logger.info(f"Scheduled indexing job {job_id} for {path}")
        elif event.type == "deleted":
            job_id = schedule_delete_job(str(path), priority=2)
            if job_id:
                logger.info(f"Scheduled deletion job {job_id} for {path}")


def start_watcher(paths: List[str], ctx: Optional[Any] = None, recursive: bool = True):
    """
    Start filesystem watcher for specified paths.
    
    Args:
        paths: List of paths to watch
        ctx: Application context
        recursive: Whether to watch subdirectories recursively
    
    Returns:
        Observer instance
    """
    if not paths:
        raise ValueError("At least one path must be provided")
    
    observer = Observer()
    handler = DocumentWatcherHandler(ctx=ctx)
    
    for path in paths:
        path_obj = Path(path)
        if not path_obj.exists():
            logger.warning(f"Path does not exist: {path}")
            continue
        
        observer.schedule(handler, str(path_obj), recursive=recursive)
        logger.info(f"Watching path: {path} (recursive={recursive})")
    
    observer.start()
    logger.info("Filesystem watcher started")
    
    return observer


def stop_watcher(observer: Observer):
    """
    Stop filesystem watcher.
    
    Args:
        observer: Observer instance to stop
    """
    if observer and observer.is_alive():
        observer.stop()
        observer.join(timeout=5.0)
        logger.info("Filesystem watcher stopped")

