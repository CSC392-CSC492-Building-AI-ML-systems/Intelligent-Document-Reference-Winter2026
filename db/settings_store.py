"""Persisted settings store backed by the settings table in local_search.db."""

import json
import sqlite3
from typing import Any, Dict


class SettingsStore:
    """Read/write key-value settings from the settings table.

    Operates on the same database as UnifiedDatabase (local_search.db).
    Uses plain sqlite3 connections (no sqlite-vec needed for this table).
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Create the settings table if it doesn't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )""")
            conn.commit()
        finally:
            conn.close()

    def get_all(self) -> Dict[str, Any]:
        """Return all settings as a dict. JSON values are deserialized."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            result: Dict[str, Any] = {}
            for row in rows:
                try:
                    result[row["key"]] = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    result[row["key"]] = row["value"]
            return result
        finally:
            conn.close()

    def get(self, key: str, default: Any = None) -> Any:
        """Return a single setting value, or *default* if not found."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        finally:
            conn.close()

    def set(self, key: str, value: Any) -> None:
        """Upsert a single setting."""
        serialized = json.dumps(value)
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                  updated_at = excluded.updated_at""",
                (key, serialized),
            )
            conn.commit()
        finally:
            conn.close()

    def set_many(self, settings: Dict[str, Any]) -> None:
        """Upsert multiple settings in one transaction."""
        conn = self._get_conn()
        try:
            with conn:
                for key, value in settings.items():
                    serialized = json.dumps(value)
                    conn.execute(
                        """INSERT INTO settings (key, value, updated_at)
                           VALUES (?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                          updated_at = excluded.updated_at""",
                        (key, serialized),
                    )
        finally:
            conn.close()

    def delete(self, key: str) -> None:
        """Remove a single setting."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()
