"""Chunking package: semantic and structural chunking, density filter, validation."""

from ingestion.chunking.semantic import (
    CandidateChunk,
    chunk_document,
    should_store_chunk,
)
from ingestion.chunking.structural import StructuralChunk, structural_chunk_document


def assert_contiguous(chunks: list[dict], *, allow_overlap: bool = False) -> None:
    """Validate that chunk intervals are unique, non-overlapping, and contiguous.

    Args:
        chunks: List of chunk dicts with ``start_offset`` and ``end_offset`` keys.
        allow_overlap: If True, skip the non-overlapping/contiguity checks and
            only verify that every chunk has a unique, non-degenerate interval.

    Raises:
        ValueError: When validation fails.
    """
    if not chunks:
        return

    sorted_chunks = sorted(chunks, key=lambda c: (c["start_offset"], c["end_offset"]))

    for i, c in enumerate(sorted_chunks):
        s, e = c["start_offset"], c["end_offset"]
        if e < s:
            raise ValueError(
                f"Chunk {i} has inverted interval: start_offset={s} > end_offset={e}"
            )

    if allow_overlap:
        return

    for i in range(1, len(sorted_chunks)):
        prev_end = sorted_chunks[i - 1]["end_offset"]
        cur_start = sorted_chunks[i]["start_offset"]
        if cur_start < prev_end:
            raise ValueError(
                f"Chunks {i - 1} and {i} overlap: prev end_offset={prev_end}, "
                f"cur start_offset={cur_start}"
            )


__all__ = [
    "CandidateChunk",
    "assert_contiguous",
    "chunk_document",
    "should_store_chunk",
    "StructuralChunk",
    "structural_chunk_document",
]
