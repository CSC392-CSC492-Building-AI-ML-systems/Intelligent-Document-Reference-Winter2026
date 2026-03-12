"""Near-duplicate removal: drop chunks with cosine similarity > threshold."""

from typing import Any, List, Tuple

import numpy as np

from ingestion.chunking.structural import StructuralChunk


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def remove_near_duplicates(
    chunks: List[StructuralChunk],
    embeddings: List[List[float]],
    threshold: float = 0.95,
) -> Tuple[List[StructuralChunk], List[List[float]]]:
    """Remove chunks with similarity > threshold. Keeps first occurrence."""
    if len(chunks) != len(embeddings) or not chunks:
        return chunks, embeddings
    kept: List[int] = [0]
    for i in range(1, len(chunks)):
        is_dup = any(
            _cosine_similarity(embeddings[i], embeddings[k]) > threshold for k in kept
        )
        if not is_dup:
            kept.append(i)
    return [chunks[i] for i in kept], [embeddings[i] for i in kept]


def remove_near_duplicates_dicts(
    chunk_dicts: List[dict[str, Any]],
    embeddings: List[List[float]],
    threshold: float = 0.95,
) -> Tuple[List[dict[str, Any]], List[List[float]]]:
    """Remove chunk dicts with similarity > threshold. Keeps first occurrence."""
    if len(chunk_dicts) != len(embeddings) or not chunk_dicts:
        return chunk_dicts, embeddings
    kept: List[int] = [0]
    for i in range(1, len(chunk_dicts)):
        if any(
            _cosine_similarity(embeddings[i], embeddings[k]) > threshold for k in kept
        ):
            continue
        kept.append(i)
    return [chunk_dicts[i] for i in kept], [embeddings[i] for i in kept]
