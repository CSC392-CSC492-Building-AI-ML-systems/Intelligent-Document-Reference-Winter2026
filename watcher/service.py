"""File tracking service — reconciles watch paths, detects changes, and schedules jobs."""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

from watcher import BaseWatcher, FileRegistry, FileScanner, get_watcher

logger = logging.getLogger(__name__)


class FileTrackingService:
    """Watches filesystem paths for changes and feeds them into a Scheduler.

    Dependencies are injected at construction time so the service can be
    tested in isolation and wired through ``AppContext``.
    """

    def __init__(
        self,
        registry: FileRegistry,
        scheduler: Optional[Any] = None,
        watcher: Optional[BaseWatcher] = None,
    ) -> None:
        self.db = registry
        self._scheduler = scheduler
        self.scanner = FileScanner([])
        self.watcher = watcher or get_watcher(self.handle_event)
        self.watch_configs: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None

    def handle_event(
        self,
        src_path: str,
        event_type: str,
        dest_path: Optional[str] = None,
    ) -> None:
        logger.info("Event detected: %s - %s", event_type, src_path)

        if event_type == "deleted":
            self.db.remove_file(src_path)
            self._schedule(src_path)
        elif event_type == "moved" and dest_path:
            self.db.remove_file(src_path)
            self._update_inventory(dest_path)
            self._schedule(dest_path)
        else:
            self._update_inventory(src_path)
            self._schedule(src_path)

    def _schedule(self, file_path: str) -> None:
        if self._scheduler is not None:
            self._scheduler.schedule(file_path, source="watcher")

    def _update_inventory(self, file_path: str) -> None:
        try:
            if os.path.exists(file_path):
                stats = os.stat(file_path)
                self.db.upsert_file(file_path, stats.st_mtime)
        except OSError:
            pass

    def _scan_and_index(
        self, path: str, excluded_files: Optional[List[str]] = None
    ) -> None:
        if os.path.isfile(path):
            # Individual file entry in monitor_config — seed watched_files and schedule directly
            logger.info("Registering individual file: %s", path)
            try:
                self.db.upsert_file(path, os.stat(path).st_mtime)
                self._schedule(path)
            except OSError:
                logger.warning("Could not stat individual file: %s", path)
            return
        logger.info("Scanning directory: %s", path)
        for _, info in self.scanner.scan_directory(path, excluded_files=excluded_files):
            self.db.upsert_file(info["path"], info["mtime"])
            self._schedule(info["path"])

    def _sync_loop(self) -> None:
        logger.info("Started config sync loop.")
        while self._running:
            try:
                self._reconcile()
            except Exception:
                logger.exception("Sync loop error")
            time.sleep(5)

    def _reconcile(self) -> None:
        new_configs = self._refresh_configs()
        desired: Set[str] = set(new_configs.keys())

        if hasattr(self.watcher, "get_watched_paths"):
            actual: Set[str] = set(self.watcher.get_watched_paths())
        else:
            actual = set(self.watch_configs.keys())

        missing = desired - actual
        extra = actual - desired

        modified: List[str] = []
        for path in desired & actual:
            old_excl = set(self.watch_configs.get(path, {}).get("excluded_files", []))
            new_excl = set(new_configs[path].get("excluded_files", []))
            if old_excl != new_excl:
                modified.append(path)

        for path in missing:
            cfg = new_configs[path]
            excluded = cfg.get("excluded_files", [])
            self.watcher.schedule_watch(path, excluded)
            if (
                hasattr(self.watcher, "get_watched_paths")
                and path in self.watcher.get_watched_paths()
            ):
                self._scan_and_index(path, excluded)
            elif not hasattr(self.watcher, "get_watched_paths"):
                self._scan_and_index(path, excluded)

        for path in extra:
            self.watcher.unschedule_watch(path)

        for path in modified:
            self.watcher.unschedule_watch(path)
            cfg = new_configs[path]
            excluded = cfg.get("excluded_files", [])
            self.watcher.schedule_watch(path, excluded)
            self._scan_and_index(path, excluded)

        # Polling fallback for individual files: watchdog's parent-dir watch
        # on macOS (FSEvents) can silently miss file-level modifications.
        # Compare current mtime against watched_files and re-schedule when
        # a change is detected.
        for path in desired & actual:
            if not os.path.isfile(path):
                continue
            try:
                current_mtime = os.stat(path).st_mtime
                state = self.db.get_file_state(path)
                if state is None:
                    # File missing from watched_files — re-seed it
                    self.db.upsert_file(path, current_mtime)
                    self._schedule(path)
                elif current_mtime != state["last_modified"]:
                    self.db.upsert_file(path, current_mtime)
                    self._schedule(path)
            except OSError:
                pass

        self.watch_configs = new_configs

    def _refresh_configs(self) -> Dict[str, Dict[str, Any]]:
        try:
            configs = self.db.get_watch_paths()
            return {c["path"]: c for c in configs}
        except Exception:
            logger.exception("Failed to refresh configs")
            return {}

    def start_background(self) -> None:
        """Non-blocking start: launches OS watcher and sync thread."""
        logger.info("FileTrackingService starting (background)...")
        self._running = True

        self.watch_configs = self._refresh_configs()
        self.watcher.start([])

        for path, cfg in self.watch_configs.items():
            excluded = cfg.get("excluded_files", [])
            self.watcher.schedule_watch(path, excluded)
            self._scan_and_index(path, excluded)

        self._sync_thread = threading.Thread(
            target=self._sync_loop, daemon=True, name="watcher-sync"
        )
        self._sync_thread.start()
        logger.info("FileTrackingService running in background")

    def start(self) -> None:
        """Blocking start — runs until interrupted. Useful for standalone use."""
        self.start_background()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        logger.info("FileTrackingService stopping...")
        self._running = False
        self.watcher.stop()
