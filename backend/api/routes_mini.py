"""Mini mode endpoints for lightweight file search using vector similarity."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.api.routes_files import load_file_indexing_config
from backend.deps import get_context
from core.context import AppContext

router = APIRouter(prefix="/mini", tags=["mini"])
logger = logging.getLogger(__name__)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


@router.get("/search")
async def mini_search(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=6, ge=1, le=12),
    ctx: AppContext = Depends(get_context),
) -> dict[str, Any]:
    """Search files using vector similarity from the embedding pipeline.

    Embeds the query, runs vector search against indexed chunks, then
    groups results by file for display in the Mini Mode widget.
    """
    if ctx.db is None or ctx.embedding_client is None:
        return {"query": q, "results": []}

    query = (q or "").strip()
    if not query:
        return {"query": query, "results": []}

    # Embed the query and run vector search
    try:
        query_vec = await asyncio.to_thread(ctx.embedding_client.embed_text, [query])
    except Exception as e:
        logger.warning("Mini search embed failed: %s", e)
        return {"query": query, "results": []}

    fetch_k = max(limit * 4, 20)
    try:
        vector_results = await asyncio.to_thread(
            ctx.db.search_with_metadata, query_vec[0], limit=fetch_k
        )
    except Exception as e:
        logger.warning("Mini search vector query failed: %s", e)
        return {"query": query, "results": []}

    # Optional: also run lexical search and merge (lightweight RRF)
    lexical_results: list[dict[str, Any]] = []
    if hasattr(ctx.db, "search_text_with_metadata"):
        try:
            lexical_results = await asyncio.to_thread(
                ctx.db.search_text_with_metadata, query, fetch_k
            )
        except Exception:
            pass

    # Fuse results by chunk key using simple RRF
    by_key: dict[str, dict[str, Any]] = {}
    score_by_key: dict[str, float] = {}
    k_rrf = 60

    for idx, row in enumerate(vector_results):
        key = f"{row.get('id')}:{row.get('file_path','')}"
        by_key[key] = row
        score_by_key[key] = score_by_key.get(key, 0.0) + 1.0 / (k_rrf + idx + 1)

    for idx, row in enumerate(lexical_results):
        key = f"{row.get('id')}:{row.get('file_path','')}"
        by_key.setdefault(key, row)
        score_by_key[key] = score_by_key.get(key, 0.0) + 1.0 / (k_rrf + idx + 1)

    ranked = sorted(score_by_key.items(), key=lambda x: x[1], reverse=True)

    # Optionally scope to context files
    cfg = load_file_indexing_config() or {}
    context_files = [str(p) for p in (cfg.get("context", {}).get("files", []) or [])]
    context_norm = {_normalize(p) for p in context_files} if context_files else set()

    # Group by file — keep the best chunk per file
    seen_files: dict[str, dict[str, Any]] = {}
    for key, rrf_score in ranked:
        row = by_key[key]
        path = str(row.get("file_path", ""))
        path_norm = _normalize(path)

        if context_norm and path_norm not in context_norm:
            continue

        if path in seen_files:
            continue

        snippet = str(row.get("text_content", "")).strip().replace("\n", " ")[:180]
        distance = row.get("distance")
        similarity = max(0.0, 1.0 - float(distance)) if distance is not None else 0.0

        seen_files[path] = {
            "file_path": path,
            "file_name": Path(path).name,
            "parent": os.path.dirname(path).replace("\\", "/"),
            "snippet": snippet,
            "score": round(rrf_score, 6),
            "similarity": round(similarity, 4),
        }

        if len(seen_files) >= limit:
            break

    results = list(seen_files.values())
    return {"query": query, "results": results}
