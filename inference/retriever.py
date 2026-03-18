"""Retrieval wrapper with file-scoped hybrid ranking."""

import asyncio
import os
import re
from typing import Any, Dict, List, Optional


class Retriever:
    def __init__(self, db: Any, embedding_client: Any):
        self.db = db
        self.embedder = embedding_client

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        folder_id: Optional[int] = None,
        file_ids: Optional[List[int]] = None,
        selected_file_paths: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Embed query and run hybrid retrieval inside selected-file scope.

        Args:
            query: Natural-language question from the user.
            top_k: How many chunks to return.
            folder_id: Optional single file-level filter (legacy).
            file_ids: Optional list of file IDs to restrict the search to.
            selected_file_paths: Optional selected files used for path-aware boosts.

        Returns:
            List of chunk dicts with text_content, file_path, distance.
        """
        # embed_text is synchronous in all current clients
        query_vec = await asyncio.to_thread(self.embedder.embed_text, [query])

        # When file_ids is an explicit empty list the user deselected all files;
        # return no results instead of falling through to an unfiltered search.
        if file_ids is not None and len(file_ids) == 0:
            return []

        fetch_k = max(top_k * 4, top_k)
        vector_results = await asyncio.to_thread(
            self.db.search_with_metadata,
            query_vec[0],
            limit=fetch_k,
            file_id=folder_id,
            file_ids=file_ids,
        )
        lexical_results: List[Dict[str, Any]] = []
        if hasattr(self.db, "search_text_with_metadata"):
            lexical_results = await asyncio.to_thread(
                self.db.search_text_with_metadata,
                query,
                fetch_k,
                folder_id,
                file_ids,
            )

        ranked = self._hybrid_rank(
            query=query,
            vector_results=vector_results,
            lexical_results=lexical_results,
            selected_file_paths=selected_file_paths,
        )
        return ranked[:top_k]

    def _hybrid_rank(
        self,
        *,
        query: str,
        vector_results: List[Dict[str, Any]],
        lexical_results: List[Dict[str, Any]],
        selected_file_paths: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Fuse vector and lexical rankings with file-aware boosts."""
        by_chunk_id: Dict[str, Dict[str, Any]] = {}
        score_by_chunk: Dict[str, float] = {}

        for idx, row in enumerate(vector_results):
            key = self._chunk_key(row)
            by_chunk_id[key] = row
            score_by_chunk[key] = score_by_chunk.get(key, 0.0) + self._rrf(idx)

        for idx, row in enumerate(lexical_results):
            key = self._chunk_key(row)
            by_chunk_id.setdefault(key, row)
            score_by_chunk[key] = score_by_chunk.get(key, 0.0) + self._rrf(idx)

        for key, row in by_chunk_id.items():
            score_by_chunk[key] = score_by_chunk.get(
                key, 0.0
            ) + self._file_metadata_boost(query, row, selected_file_paths)

        ranked_pairs = sorted(
            score_by_chunk.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        ranked_rows: List[Dict[str, Any]] = []
        for chunk_key, hybrid_score in ranked_pairs:
            row = dict(by_chunk_id[chunk_key])
            row["hybrid_score"] = round(float(hybrid_score), 6)
            ranked_rows.append(row)
        return ranked_rows

    @staticmethod
    def _chunk_key(row: Dict[str, Any]) -> str:
        chunk_id = row.get("id")
        path = row.get("file_path", "")
        content = row.get("text_content", "")
        return f"{chunk_id}:{path}:{content[:48]}"

    @staticmethod
    def _rrf(rank_index: int, k: int = 60) -> float:
        return 1.0 / float(k + rank_index + 1)

    def _file_metadata_boost(
        self,
        query: str,
        row: Dict[str, Any],
        selected_file_paths: Optional[List[str]],
    ) -> float:
        """Compute small precision-oriented boosts using path metadata."""
        score = 0.0
        query_lower = query.lower()
        path = str(row.get("file_path", "")).lower()
        basename = os.path.basename(path)
        stem, ext = os.path.splitext(basename)

        query_terms = set(re.findall(r"[a-z0-9_\-.]+", query_lower))
        stem_terms = set(re.findall(r"[a-z0-9_]+", stem))

        if basename and basename in query_lower:
            score += 0.40
        if stem and stem in query_lower:
            score += 0.25
        if ext and ext in query_terms:
            score += 0.20

        overlap = len(query_terms & stem_terms)
        if overlap > 0:
            score += min(0.20, 0.05 * overlap)

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
        image_terms = {"image", "photo", "picture", "screenshot", "diagram", "png"}
        if ext in image_exts and any(t in query_terms for t in image_terms):
            score += 0.15

        if selected_file_paths and len(selected_file_paths) == 1:
            only_selected = selected_file_paths[0].lower()
            if path == only_selected:
                score += 0.15

        return score
