"""Semantic chunker: builds chunks from blocks and applies a heuristic to decide which to store.

Consumes chunker-ready StructuredDocument (after preprocessing). Produces chunk dicts
suitable for the DB (chunk_id, chunk_index, start_offset, end_offset, text_content)
only for chunks that pass the store heuristic.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

from ingestion.models import (
    BlockType,
    ContentBlock,
    StructuredDocument,
    estimate_tokens,
)


@dataclass
class CandidateChunk:
    """A single candidate chunk (one or more merged blocks) before the store heuristic."""

    text: str
    block_types: tuple[BlockType, ...]
    token_estimate: int
    start_offset: int  # character offset in logical document
    end_offset: int
    page_number: Optional[int] = None
    section_hierarchy: tuple[str, ...] = ()


def _split_large_text(text: str, max_chars: int) -> List[str]:
    """Split text exceeding *max_chars* into smaller segments.

    Prefers paragraph boundaries (``\\n\\n``), then sentence boundaries,
    then hard-splits at *max_chars* as a last resort.
    """
    if len(text) <= max_chars:
        return [text]

    # 1. Split at paragraph boundaries
    paragraphs = text.split("\n\n")
    segments: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        added_len = len(para) + (2 if current else 0)
        if current_len + added_len > max_chars and current:
            segments.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += added_len
    if current:
        segments.append("\n\n".join(current))

    # 2. Split oversized segments at sentence boundaries
    refined: List[str] = []
    for seg in segments:
        if len(seg) <= max_chars:
            refined.append(seg)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", seg)
        cur: List[str] = []
        cur_len = 0
        for sent in sentences:
            added = len(sent) + (1 if cur else 0)
            if cur_len + added > max_chars and cur:
                refined.append(" ".join(cur))
                cur = [sent]
                cur_len = len(sent)
            else:
                cur.append(sent)
                cur_len += added
        if cur:
            refined.append(" ".join(cur))

    # 3. Hard-split anything still oversized
    result: List[str] = []
    for seg in refined:
        while len(seg) > max_chars:
            result.append(seg[:max_chars])
            seg = seg[max_chars:]
        if seg:
            result.append(seg)

    return result


def _merge_blocks_into_chunks(
    blocks: List[ContentBlock],
    min_chars: int = 0,
    max_chars: int = 2500,
) -> List[CandidateChunk]:
    """Merge consecutive blocks into candidate chunks within size bounds.

    - Large single blocks are split at paragraph / sentence boundaries first.
    - Code blocks and tables are kept as single chunks (not merged with neighbors).
    - Other blocks are merged until total length is in [min_chars, max_chars] or
      a non-mergeable block is hit.
    """
    if not blocks:
        return []

    candidates: List[CandidateChunk] = []
    i = 0
    offset = 0

    while i < len(blocks):
        block = blocks[i]
        content = block.content
        start = offset

        meta = block.metadata
        page = meta.page_number if meta else None
        section = meta.section_hierarchy if meta else ()

        # Standalone: code, table — one block = one chunk (split if oversized)
        if block.block_type in (BlockType.CODE_BLOCK, BlockType.TABLE):
            segments = (
                _split_large_text(content, max_chars)
                if len(content) > max_chars
                else [content]
            )
            for seg in segments:
                seg_start = offset
                seg_end = offset + len(seg)
                candidates.append(
                    CandidateChunk(
                        text=seg,
                        block_types=(block.block_type,),
                        token_estimate=estimate_tokens(seg),
                        start_offset=seg_start,
                        end_offset=seg_end,
                        page_number=page,
                        section_hierarchy=section,
                    )
                )
                offset = seg_end + 2
            i += 1
            continue

        # If a single text block exceeds max_chars, split it first
        if len(content) > max_chars:
            segments = _split_large_text(content, max_chars)
            for seg in segments:
                seg_start = offset
                seg_end = offset + len(seg)
                candidates.append(
                    CandidateChunk(
                        text=seg,
                        block_types=(block.block_type,),
                        token_estimate=estimate_tokens(seg),
                        start_offset=seg_start,
                        end_offset=seg_end,
                        page_number=page,
                        section_hierarchy=section,
                    )
                )
                offset = seg_end + 2
            i += 1
            continue

        # Advance offset past this block's content
        offset += len(content) + (1 if content and not content.endswith("\n") else 0)

        # Merge consecutive text-like blocks up to max_chars
        parts: List[str] = [content]
        types: List[BlockType] = [block.block_type]
        total_chars = len(content)
        j = i + 1

        while j < len(blocks):
            next_block = blocks[j]
            if next_block.block_type in (BlockType.CODE_BLOCK, BlockType.TABLE):
                break
            next_content = next_block.content
            if total_chars + len(next_content) > max_chars and total_chars >= min_chars:
                break
            parts.append(next_content)
            types.append(next_block.block_type)
            total_chars += len(next_content)
            j += 1

        text = "\n\n".join(parts)
        end_offset = start + len(text)
        token_est = estimate_tokens(text)
        candidates.append(
            CandidateChunk(
                text=text,
                block_types=tuple(types),
                token_estimate=token_est,
                start_offset=start,
                end_offset=end_offset,
                page_number=page,
                section_hierarchy=section,
            )
        )
        offset = end_offset + 2  # \n\n before next chunk
        i = j

    return candidates


# --- Heuristic: should we store this chunk? ---


def _is_likely_boilerplate(text: str) -> bool:
    """True if chunk looks like boilerplate (page numbers, all caps, mostly numbers)."""
    if not text or len(text.strip()) < 10:
        return True
    stripped = text.strip()
    # Mostly digits/punctuation/whitespace
    alpha = sum(1 for c in stripped if c.isalpha())
    if alpha < len(stripped) * 0.15:
        return True
    # All caps and short
    if len(stripped) < 100 and stripped.isupper():
        return True
    # Single repeated character or same word repeated
    words = re.findall(r"\w+", stripped)
    if len(words) >= 3 and len(set(w.lower() for w in words)) == 1:
        return True
    return False


def should_store_chunk(
    chunk: CandidateChunk,
    *,
    min_chars: int = 30,
    max_chars: int = 30_000,
    min_tokens: int = 5,
    max_tokens: int = 8000,
    store_block_types: Optional[tuple[BlockType, ...]] = None,
    skip_block_types: tuple[BlockType, ...] = (),
    skip_boilerplate: bool = True,
) -> bool:
    """Heuristic: decide whether to store this chunk.

    Args:
        chunk: Candidate chunk from block merging.
        min_chars: Skip if text length < this.
        max_chars: Skip if text length > this (e.g. embedder limit).
        min_tokens: Skip if token estimate < this.
        max_tokens: Skip if token estimate > this.
        store_block_types: If set, only store chunks that contain at least one of these.
        skip_block_types: Never store chunks that are purely these types.
        skip_boilerplate: Apply boilerplate detection (page numbers, all caps, etc.).

    Returns:
        True if the chunk should be stored.
    """
    text = chunk.text
    n_chars = len(text)
    if n_chars < min_chars or n_chars > max_chars:
        return False
    if chunk.token_estimate < min_tokens or chunk.token_estimate > max_tokens:
        return False
    if skip_block_types and all(bt in skip_block_types for bt in chunk.block_types):
        return False
    if store_block_types and not any(
        bt in store_block_types for bt in chunk.block_types
    ):
        return False
    if skip_boilerplate and _is_likely_boilerplate(text):
        return False
    return True


def chunk_document(
    document: StructuredDocument,
    *,
    min_block_chars: int = 500,
    max_block_chars: int = 2500,
    min_chars_store: int = 30,
    max_chars_store: int = 30_000,
    min_tokens_store: int = 5,
    max_tokens_store: int = 8000,
    store_block_types: Optional[tuple[BlockType, ...]] = None,
    skip_block_types: tuple[BlockType, ...] = (),
    skip_boilerplate: bool = True,
) -> List[dict[str, Any]]:
    """Build candidate chunks from document blocks and return only those to store.

    Uses block merging (respecting min/max block sizes) then applies the store
    heuristic. Output format matches what UnifiedDatabase.add_document expects.

    Args:
        document: Preprocessed StructuredDocument (chunker-ready).
        min_block_chars: Minimum target size when merging blocks (0 = no merging).
        max_block_chars: Maximum size of a merged chunk.
        min_chars_store: Heuristic: do not store chunks shorter than this.
        max_chars_store: Heuristic: do not store chunks longer than this.
        min_tokens_store: Heuristic: do not store chunks with fewer tokens.
        max_tokens_store: Heuristic: do not store chunks with more tokens.
        store_block_types: If set, only store chunks containing one of these types.
        skip_block_types: Never store chunks that are purely these types.
        skip_boilerplate: Whether to filter likely boilerplate.

    Returns:
        List of chunk dicts with chunk_id, chunk_index, start_offset, end_offset, text_content.
    """
    if not document.blocks:
        return []

    candidates = _merge_blocks_into_chunks(
        document.blocks,
        min_chars=min_block_chars,
        max_chars=max_block_chars,
    )

    out: List[dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        if not should_store_chunk(
            cand,
            min_chars=min_chars_store,
            max_chars=max_chars_store,
            min_tokens=min_tokens_store,
            max_tokens=max_tokens_store,
            store_block_types=store_block_types,
            skip_block_types=skip_block_types,
            skip_boilerplate=skip_boilerplate,
        ):
            continue
        entry: dict[str, Any] = {
            "chunk_id": str(uuid.uuid4()),
            "chunk_index": len(out),
            "start_offset": cand.start_offset,
            "end_offset": cand.end_offset,
            "text_content": cand.text,
        }
        if cand.page_number is not None:
            entry["page_number"] = cand.page_number
        if cand.section_hierarchy:
            entry["section"] = " > ".join(cand.section_hierarchy)
        out.append(entry)
    return out
