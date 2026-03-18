import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import sqlite_vec


class UnifiedDatabase:
    """Unified Database handling both Metadata (relational) and Vectors (embeddings).

    Replaces MetadataManager and VectorDB implementations.
    """

    def __init__(self, db_path: str = "local_search.db") -> None:
        """Initialize the Unified Database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection.

        Returns:
            A configured sqlite3.Connection object with row factory and extensions loaded.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _init_db(self) -> None:
        """Execute the schema.sql to initialize tables.

        Raises:
            FileNotFoundError: If schema.sql is missing.
        """
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        conn = self._get_conn()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        except Exception as e:
            # Table already exists error is common and fine
            print(f"DB Init/Check: {e}")
        finally:
            conn.close()

    def register_file(
        self, path: str, file_hash: str, size: int, modified: float
    ) -> int:
        """Upsert a file record.

        Args:
            path: The file path.
            file_hash: The hash of the file content.
            size: Size of the file in bytes.
            modified: Last modified timestamp.

        Returns:
            The ID of the file record.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Check if exists
            cursor.execute("SELECT id, file_hash FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()

            if row:
                file_id = row["id"]
                # If hash changed, update status
                if row["file_hash"] != file_hash:
                    cursor.execute(
                        """
                        UPDATE files
                        SET file_hash=?, size_bytes=?, last_modified_timestamp=?, status='outdated'
                        WHERE id=?
                        """,
                        (file_hash, size, modified, file_id),
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO files (path, file_hash, size_bytes, last_modified_timestamp, status)
                    VALUES (?, ?, ?, ?, 'pending')
                    RETURNING id
                    """,
                    (path, file_hash, size, modified),
                )
                file_id = cursor.fetchone()[0]

            conn.commit()
            return file_id
        finally:
            conn.close()

    def create_version(self, file_id: int, file_hash: str) -> int:
        """Create a version record for a file ingestion run.

        Args:
            file_id: The ID of the file.
            file_hash: The version hash.

        Returns:
            The ID of the new version record.
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                INSERT INTO file_versions (file_id, version_hash)
                VALUES (?, ?)
                RETURNING id
                """,
                (file_id, file_hash),
            )
            version_id = cursor.fetchone()[0]
            conn.commit()
            return version_id
        finally:
            conn.close()

    def add_document(
        self,
        file_id: int,
        version_id: int,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> None:
        """Transactional insert of chunks and embeddings.

        Args:
            file_id: The ID of the file.
            version_id: The ID of the version.
            chunks: List of dictionaries with keys (id/chunk_id, chunk_index,
                start_offset, end_offset, text_content).
            embeddings: List of float lists matching chunks.

        Raises:
            ValueError: If chunks and embeddings lengths do not match.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch"
            )

        conn = self._get_conn()
        try:
            with conn:  # Atomic Transaction
                for chunk, vector in zip(chunks, embeddings):
                    # 1. Insert Metadata
                    # Use chunk_id from 'id' or 'chunk_id' field.
                    c_uuid = chunk.get("id") or chunk.get("chunk_id")

                    cur = conn.execute(
                        """
                        INSERT INTO chunks (chunk_id, file_id, version_id, chunk_index, start_offset, end_offset, text_content)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            c_uuid,
                            file_id,
                            version_id,
                            chunk.get("chunk_index", 0),
                            chunk.get("start_offset", 0),
                            chunk.get("end_offset", 0),
                            chunk.get("text_content", ""),
                        ),
                    )
                    row_id = cur.lastrowid

                    # 2. Insert Vector using the SAME Row ID
                    vec_blob = sqlite_vec.serialize_float32(vector)
                    conn.execute(
                        "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                        (row_id, vec_blob),
                    )
        finally:
            conn.close()

    def search(
        self, query_vector: List[float], limit: int = 5, file_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity.

        Args:
            query_vector: The embedding vector to search for.
            limit: Maximum number of results to return.
            file_id: Optional file_id to filter by.

        Returns:
            List of joined chunk data with distance.
        """
        conn = self._get_conn()
        try:
            query_blob = sqlite_vec.serialize_float32(query_vector)

            # Base query
            sql = """
                SELECT
                    c.id, c.chunk_id, c.text_content, c.file_id,
                    vec_distance_cosine(v.embedding, ?) as distance
                FROM vec_items v
                JOIN chunks c ON v.rowid = c.id
                WHERE v.embedding MATCH ?
                  AND k = ?
            """
            params = [query_blob, query_blob, limit]

            # Note: Hard filtering (AND c.file_id = ?) with MATCH and limit
            # might reduce results if top-K vectors don't match the filter.
            # Ideally perform over-fetching or use hybrid search approaches.
            if file_id:
                # We append simple WHERE but verify behavior
                sql += " AND c.file_id = ?"
                params.append(file_id)

            sql += " ORDER BY distance"

            cursor = conn.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
            return results
        finally:
            conn.close()

    def get_file_content(self, file_id: int) -> Optional[str]:
        """Retrieve the content of a file by ID.

        Args:
            file_id: The ID of the file.

        Returns:
            The content of the file as a string, or None if not found/error.
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT path FROM files WHERE id = ?", (file_id,))
            res = cursor.fetchone()
            if res and os.path.exists(res["path"]):
                with open(res["path"], "r", errors="ignore") as f:
                    return f.read()
            return None
        finally:
            conn.close()

    def search_with_metadata(
        self,
        query_vector: List[float],
        limit: int = 5,
        file_id: Optional[int] = None,
        file_ids: Optional[List[int]] = None,
    ):
        """Joins chunks with files to provide the 'file_path' required for citations.

        Args:
            query_vector: Embedding vector for the query.
            limit: Maximum number of results to return.
            file_id: Single file-level filter (legacy, use *file_ids* for multi-file).
            file_ids: List of file IDs to restrict the search to.
        """
        conn = self._get_conn()
        try:
            query_blob = sqlite_vec.serialize_float32(query_vector)

            sql = """
                SELECT c.id, c.text_content, f.path as file_path, 
                    vec_distance_cosine(v.embedding, ?) as distance
                FROM vec_items v
                JOIN chunks c ON v.rowid = c.id
                JOIN files f ON c.file_id = f.id
                WHERE v.embedding MATCH ? AND k = ?
            """
            params: list = [query_blob, query_blob, limit]
            if file_ids:
                placeholders = ",".join("?" for _ in file_ids)
                sql += f" AND c.file_id IN ({placeholders})"
                params.extend(file_ids)
            elif file_id:
                sql += " AND c.file_id = ?"
                params.append(file_id)

            return [
                dict(row)
                for row in conn.execute(sql + " ORDER BY distance", params).fetchall()
            ]
        finally:
            conn.close()

    def get_file_record(self, file_path: str) -> Optional[dict]:
        """
        Retrieves file metadata needed for change detection.
        Returns a dictionary with file_hash and last_modified_timestamp, or None.
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT file_hash, last_modified_timestamp FROM files WHERE path = ?",
                (file_path,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def remove_file(self, file_path: str) -> None:
        """
        Removes a file and all associated data from the database.
        Due to CASCADE DELETE, this will remove chunks, versions, etc.
        Also removes associated vectors.
        """
        conn = self._get_conn()
        try:
            # First, delete vectors for chunks of this file
            conn.execute(
                """
                DELETE FROM vec_items
                WHERE rowid IN (
                    SELECT c.id FROM chunks c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.path = ?
                )
            """,
                (file_path,),
            )

            # Then delete the file (cascades to chunks, versions, etc.)
            conn.execute("DELETE FROM files WHERE path = ?", (file_path,))
            conn.commit()
        finally:
            conn.close()

    def mark_file_indexed(self, file_id: int) -> None:
        """Set file status to 'indexed' and update last_indexed_at timestamp."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE files SET status = 'indexed', last_indexed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def update_file_metadata(self, file_path: str, modified: float) -> None:
        """
        Updates only the metadata (last_modified_timestamp) for a file.
        Used for METADATA_UPDATE strategy.
        """
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE files SET last_modified_timestamp = ? WHERE path = ?",
                (modified, file_path),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_file_statuses(self) -> Dict[str, str]:
        """Return a mapping of file path -> status for every tracked file.

        Status values: 'indexed', 'pending', 'failed', 'outdated'.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT path, status FROM files").fetchall()
            return {row["path"]: row["status"] for row in rows}
        finally:
            conn.close()

    def remove_files_under_directory(self, directory_path: str) -> int:
        """Remove all indexed files whose path starts with *directory_path*.

        Deletes vectors first (required before CASCADE on files), then files.

        Returns:
            Number of files removed.
        """
        # Ensure trailing separator for prefix match
        prefix = directory_path.rstrip(os.sep) + os.sep
        conn = self._get_conn()
        try:
            # Delete vectors for all chunks under this directory
            conn.execute(
                """
                DELETE FROM vec_items
                WHERE rowid IN (
                    SELECT c.id FROM chunks c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.path LIKE ? OR f.path = ?
                )
                """,
                (prefix + "%", directory_path),
            )
            cursor = conn.execute(
                "DELETE FROM files WHERE path LIKE ? OR path = ?",
                (prefix + "%", directory_path),
            )
            removed = cursor.rowcount
            conn.commit()
            return removed
        finally:
            conn.close()

    def get_file_ids_for_paths(self, file_paths: List[str]) -> List[int]:
        """Return file IDs for the given paths (exact match or prefix for directories).

        Paths ending with os.sep are treated as directory prefixes.
        """
        if not file_paths:
            return []
        conn = self._get_conn()
        try:
            ids: List[int] = []
            for fp in file_paths:
                if os.path.isdir(fp):
                    prefix = fp.rstrip(os.sep) + os.sep
                    rows = conn.execute(
                        "SELECT id FROM files WHERE path LIKE ?",
                        (prefix + "%",),
                    ).fetchall()
                    ids.extend(row["id"] for row in rows)
                else:
                    row = conn.execute(
                        "SELECT id FROM files WHERE path = ?", (fp,)
                    ).fetchone()
                    if row:
                        ids.append(row["id"])
            return ids
        finally:
            conn.close()
