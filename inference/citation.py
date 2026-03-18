"""Citation formatting helpers."""

import os
from typing import Any, Dict, List


def format_citations(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract unique citations from retrieved chunks.

    Args:
        chunks: List of chunk dicts returned by search_with_metadata,
                each containing at least 'file_path' and optionally 'distance',
                'text_content', and 'chunk_index'.

    Returns:
        Deduplicated list of citation dicts matching the frontend Citation interface.
    """
    seen = set()
    citations: List[Dict[str, Any]] = []
    for chunk in chunks:
        path = chunk.get("file_path", "unknown")
        if path not in seen:
            seen.add(path)
            snippet = chunk.get("text_content", "")
            citations.append(
                {
                    "file_path": path,
                    "file_name": os.path.basename(path),
                    "snippet": snippet[:300] if snippet else "",
                    "relevance_score": round(1.0 - chunk.get("distance", 0.0), 4),
                    "chunk_index": chunk.get("chunk_index", 0),
                }
            )
    return citations
