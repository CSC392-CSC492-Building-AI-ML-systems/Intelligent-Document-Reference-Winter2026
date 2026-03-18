import sqlite3
from typing import Any, Dict, List, Optional


class FileRegistry:
    def __init__(self, db_path: str = "file_registry.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watched_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    last_modified REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitor_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    recursive BOOLEAN DEFAULT 1,
                    excluded_files TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Drop legacy processing_queue if it exists (replaced by jobs table)
            cursor.execute("DROP TABLE IF EXISTS processing_queue")
            conn.commit()

    def upsert_file(self, path: str, last_modified: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO watched_files (path, last_modified)
                VALUES (?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    last_modified=excluded.last_modified
            """,
                (path, last_modified),
            )
            conn.commit()

    def add_watch_path(self, path: str, excluded_files: List[str] = None):
        import json

        if excluded_files is None:
            excluded_files = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO monitor_config (path, excluded_files, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(path) DO UPDATE SET
                    excluded_files=excluded.excluded_files,
                    is_active=1
            """,
                (path, json.dumps(excluded_files)),
            )
            conn.commit()

    def get_watch_paths(self) -> List[Dict[str, Any]]:
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monitor_config WHERE is_active = 1")
            rows = cursor.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["excluded_files"] = (
                    json.loads(d["excluded_files"]) if d["excluded_files"] else []
                )
                results.append(d)
            return results

    def get_all_monitor_paths(self) -> List[str]:
        """Return all paths in monitor_config (active and inactive), for syncing with inclusion list."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM monitor_config")
            return [row[0] for row in cursor.fetchall()]

    def remove_watch_path(self, path: str):
        """Deactivate a monitor_config entry and remove associated watched_files."""
        import os

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE monitor_config SET is_active = 0 WHERE path = ?", (path,)
            )
            # Also clean watched_files under this path (directory prefix or exact)
            prefix = path.rstrip(os.sep) + os.sep
            cursor.execute(
                "DELETE FROM watched_files WHERE path LIKE ? OR path = ?",
                (prefix + "%", path),
            )
            conn.commit()

    def remove_watch_path_by_id(self, id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE monitor_config SET is_active = 0 WHERE id = ?", (id,)
            )
            conn.commit()

    def get_file_state(self, path: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM watched_files WHERE path = ?", (path,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "path": row[1], "last_modified": row[2]}
            return None

    def remove_file(self, path: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM watched_files WHERE path = ?", (path,))
            conn.commit()
