"""Structural chunking: 300-700 tokens, ≤10% overlap, structure-aware."""

import uuid
from dataclasses import dataclass
from typing import Any, List

from ingestion.models import (
    BlockType,
    StructuredDocument,
    estimate_tokens,
)


@dataclass
class StructuralChunk:
    """A chunk from structural chunking with metadata."""

    chunk_id: str
    text: str
    chunk_index: int
    start_offset: int
    end_offset: int
    token_count: int
    section_hierarchy: tuple[str, ...] = ()
    page_number: int | None = None
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "text_content": self.text,
            "token_count": self.token_count,
            "section_hierarchy": list(self.section_hierarchy),
            "page_number": self.page_number,
            "file_path": self.file_path,
        }


def _take_tail_tokens(text: str, n_tokens: int) -> str:
    words = text.split()
    approx = int(n_tokens * 1.3)
    if len(words) <= approx:
        return text
    return " ".join(words[-approx:])


def structural_chunk_document(
    document: StructuredDocument,
    *,
    min_tokens: int = 300,
    max_tokens: int = 700,
    overlap_tokens: int = 50,
    max_overlap_ratio: float = 0.10,
) -> List[StructuralChunk]:
    """Chunk document with structure awareness, token targets, and overlap."""
    if not document.blocks:
        return []

    eff_overlap = min(overlap_tokens, max(0, int(max_tokens * max_overlap_ratio)))
    chunks: List[StructuralChunk] = []
    acc: List[str] = []
    acc_tokens = 0
    chunk_start = 0
    last_section: tuple[str, ...] = ()
    last_page: int | None = None
    overlap_tail = ""
    chunk_idx = 0

    def flush(
        t: str, start: int, end: int, section: tuple[str, ...], page: int | None
    ) -> str:
        nonlocal chunk_idx
        tail = _take_tail_tokens(t, eff_overlap) if eff_overlap > 0 else ""
        chunks.append(
            StructuralChunk(
                chunk_id=str(uuid.uuid4()),
                text=t,
                chunk_index=chunk_idx,
                start_offset=start,
                end_offset=end,
                token_count=estimate_tokens(t),
                section_hierarchy=section,
                page_number=page,
                file_path=document.source_id,
            )
        )
        chunk_idx += 1
        return tail

    doc_offset = 0
    for block in document.blocks:
        content = block.content.strip()
        if not content:
            continue
        section = block.metadata.section_hierarchy or ()
        page = block.metadata.page_number
        bt = estimate_tokens(content)

        # Prepend overlap context from previous chunk without affecting offsets.
        # overlap_tail is duplicate text already counted in doc_offset, so we
        # must NOT advance doc_offset or change chunk_start for it.
        if overlap_tail:
            acc = [overlap_tail] + acc
            acc_tokens += estimate_tokens(overlap_tail)
            overlap_tail = ""

        if block.block_type == BlockType.HEADING and acc and acc_tokens >= min_tokens:
            text = "\n\n".join(acc)
            overlap_tail = flush(text, chunk_start, doc_offset, last_section, last_page)
            acc = []
            acc_tokens = 0
            chunk_start = doc_offset

        if bt > max_tokens:
            if acc and acc_tokens >= min_tokens:
                text = "\n\n".join(acc)
                overlap_tail = flush(
                    text, chunk_start, doc_offset, last_section, last_page
                )
                acc = []
                acc_tokens = 0
                chunk_start = doc_offset
            for para in content.split("\n\n"):
                pt = estimate_tokens(para)
                if acc_tokens + pt <= max_tokens:
                    acc.append(para)
                    acc_tokens += pt
                else:
                    if acc and acc_tokens >= min_tokens:
                        text = "\n\n".join(acc)
                        overlap_tail = flush(
                            text, chunk_start, doc_offset, section, page
                        )
                        chunk_start = doc_offset
                    acc = [para]
                    acc_tokens = pt
                doc_offset += len(para) + 2
            last_section = section
            last_page = page
            continue

        if acc_tokens + bt > max_tokens and acc_tokens >= min_tokens:
            text = "\n\n".join(acc)
            overlap_tail = flush(text, chunk_start, doc_offset, last_section, last_page)
            acc = []
            acc_tokens = 0
            chunk_start = doc_offset

        acc.append(content)
        acc_tokens += bt
        doc_offset += len(content) + 2
        last_section = section
        last_page = page

    # Prepend any remaining overlap context before the final flush
    if overlap_tail:
        acc = [overlap_tail] + acc
        overlap_tail = ""

    if acc:
        text = "\n\n".join(acc)
        flush(text, chunk_start, doc_offset, last_section, last_page)

    return chunks
