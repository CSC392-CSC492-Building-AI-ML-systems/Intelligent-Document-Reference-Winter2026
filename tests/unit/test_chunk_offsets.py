"""Tests for chunk interval correctness: unique, non-overlapping offsets and contiguity."""

import pytest

from ingestion.chunking import assert_contiguous, chunk_document
from ingestion.chunking.semantic import (
    _merge_blocks_into_chunks,
    _split_large_text,
)
from ingestion.chunking.structural import structural_chunk_document
from ingestion.models import (
    BlockMetadata,
    BlockType,
    ContentBlock,
    ExtractionMethod,
    SourceModality,
    StructuredDocument,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_block(
    content: str, block_type: BlockType = BlockType.PARAGRAPH
) -> ContentBlock:
    return ContentBlock(
        content=content,
        block_type=block_type,
        source_modality=SourceModality.TEXT,
        metadata=BlockMetadata(extraction_method=ExtractionMethod.NATIVE),
    )


def _make_doc(blocks: list[ContentBlock]) -> StructuredDocument:
    return StructuredDocument(
        source_id="test",
        blocks=blocks,
        source_modality=SourceModality.TEXT,
    )


# ---------------------------------------------------------------------------
# _split_large_text
# ---------------------------------------------------------------------------


class TestSplitLargeText:
    def test_no_split_needed(self):
        text = "short text"
        assert _split_large_text(text, 1000) == [text]

    def test_splits_at_paragraph_boundary(self):
        paras = ["A" * 200, "B" * 200, "C" * 200]
        text = "\n\n".join(paras)
        segments = _split_large_text(text, 250)
        assert len(segments) >= 2
        for seg in segments:
            assert len(seg) <= 250

    def test_hard_split_for_huge_block(self):
        text = "X" * 5000
        segments = _split_large_text(text, 1000)
        assert all(len(s) <= 1000 for s in segments)
        assert "".join(segments) == text


# ---------------------------------------------------------------------------
# Semantic chunker: _merge_blocks_into_chunks
# ---------------------------------------------------------------------------


class TestSemanticOffsets:
    def test_single_block_within_limit(self):
        blocks = [_make_block("Hello world")]
        candidates = _merge_blocks_into_chunks(blocks, min_chars=0, max_chars=500)
        assert len(candidates) == 1
        assert candidates[0].start_offset == 0
        assert candidates[0].end_offset == len("Hello world")

    def test_multiple_blocks_merged(self):
        blocks = [_make_block("Block one"), _make_block("Block two")]
        candidates = _merge_blocks_into_chunks(blocks, min_chars=0, max_chars=5000)
        assert len(candidates) == 1
        text = candidates[0].text
        assert "Block one" in text and "Block two" in text
        assert candidates[0].start_offset == 0
        assert candidates[0].end_offset == len(text)

    def test_blocks_split_by_max_chars(self):
        blocks = [
            _make_block("A" * 300),
            _make_block("B" * 300),
            _make_block("C" * 300),
        ]
        candidates = _merge_blocks_into_chunks(blocks, min_chars=100, max_chars=400)
        assert len(candidates) >= 2
        # Offsets must be strictly increasing
        for i in range(1, len(candidates)):
            assert candidates[i].start_offset >= candidates[i - 1].end_offset

    def test_large_single_block_gets_split(self):
        """A block exceeding max_chars is split into multiple candidates."""
        big = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        blocks = [_make_block(big)]
        candidates = _merge_blocks_into_chunks(blocks, min_chars=0, max_chars=20)
        assert len(candidates) > 1
        for c in candidates:
            assert c.end_offset > c.start_offset
        # No overlapping intervals
        for i in range(1, len(candidates)):
            assert candidates[i].start_offset >= candidates[i - 1].end_offset

    def test_code_block_kept_standalone(self):
        blocks = [
            _make_block("intro text"),
            _make_block("def foo(): pass", BlockType.CODE_BLOCK),
            _make_block("outro text"),
        ]
        candidates = _merge_blocks_into_chunks(blocks, min_chars=0, max_chars=5000)
        code_cands = [c for c in candidates if BlockType.CODE_BLOCK in c.block_types]
        assert len(code_cands) == 1
        assert code_cands[0].text == "def foo(): pass"


# ---------------------------------------------------------------------------
# chunk_document (semantic)
# ---------------------------------------------------------------------------


class TestChunkDocumentOffsets:
    def test_offsets_are_non_overlapping(self):
        blocks = [
            _make_block(f"Paragraph {i} has some varied content here. " * 10)
            for i in range(5)
        ]
        doc = _make_doc(blocks)
        chunks = chunk_document(
            doc,
            min_block_chars=50,
            max_block_chars=300,
            min_chars_store=10,
            min_tokens_store=1,
        )
        assert len(chunks) >= 2
        sorted_chunks = sorted(chunks, key=lambda c: c["start_offset"])
        for i in range(1, len(sorted_chunks)):
            assert (
                sorted_chunks[i]["start_offset"] >= sorted_chunks[i - 1]["end_offset"]
            ), f"Chunk {i} overlaps with chunk {i-1}"

    def test_each_chunk_has_unique_interval(self):
        blocks = [
            _make_block(f"Section {i} discusses various topics in detail. " * 8)
            for i in range(4)
        ]
        doc = _make_doc(blocks)
        chunks = chunk_document(
            doc,
            min_block_chars=50,
            max_block_chars=300,
            min_chars_store=10,
            min_tokens_store=1,
        )
        intervals = [(c["start_offset"], c["end_offset"]) for c in chunks]
        assert len(intervals) == len(set(intervals)), "Duplicate intervals found"

    def test_assert_contiguous_passes(self):
        blocks = [_make_block("Sentence. " * 30) for _ in range(6)]
        doc = _make_doc(blocks)
        chunks = chunk_document(
            doc,
            min_block_chars=50,
            max_block_chars=250,
            min_chars_store=10,
            min_tokens_store=1,
        )
        if len(chunks) >= 2:
            assert_contiguous(chunks)  # should not raise


# ---------------------------------------------------------------------------
# Structural chunker
# ---------------------------------------------------------------------------


class TestStructuralOffsets:
    def _make_large_doc(
        self, n_blocks: int = 8, chars_per_block: int = 800
    ) -> StructuredDocument:
        blocks = [
            _make_block("Word " * (chars_per_block // 5)) for _ in range(n_blocks)
        ]
        return _make_doc(blocks)

    def test_no_block_lost(self):
        """Every block's content must appear in at least one chunk."""
        blocks = [_make_block(f"UniqueContent{i} " * 40) for i in range(6)]
        doc = _make_doc(blocks)
        chunks = structural_chunk_document(
            doc, min_tokens=50, max_tokens=200, overlap_tokens=20
        )
        combined = " ".join(c.text for c in chunks)
        for i in range(6):
            assert f"UniqueContent{i}" in combined, f"Block {i} content lost"

    def test_offsets_strictly_increasing(self):
        doc = self._make_large_doc(n_blocks=10)
        chunks = structural_chunk_document(
            doc, min_tokens=50, max_tokens=200, overlap_tokens=20
        )
        for i in range(1, len(chunks)):
            assert (
                chunks[i].start_offset >= chunks[i - 1].end_offset
            ), f"Chunk {i} start ({chunks[i].start_offset}) < chunk {i-1} end ({chunks[i-1].end_offset})"

    def test_offsets_non_overlapping(self):
        doc = self._make_large_doc(n_blocks=8)
        chunks = structural_chunk_document(
            doc, min_tokens=50, max_tokens=200, overlap_tokens=30
        )
        chunk_dicts = [c.to_dict() for c in chunks]
        if len(chunk_dicts) >= 2:
            assert_contiguous(chunk_dicts)  # should not raise

    def test_zero_overlap_produces_distinct_offsets(self):
        doc = self._make_large_doc(n_blocks=6)
        chunks = structural_chunk_document(
            doc, min_tokens=50, max_tokens=200, overlap_tokens=0
        )
        intervals = [(c.start_offset, c.end_offset) for c in chunks]
        assert len(intervals) == len(
            set(intervals)
        ), "Duplicate intervals with zero overlap"

    def test_final_flush_includes_overlap(self):
        """overlap_tail must be prepended before the final flush so no content is lost."""
        blocks = [_make_block("Word " * 60) for _ in range(4)]
        doc = _make_doc(blocks)
        chunks = structural_chunk_document(
            doc, min_tokens=30, max_tokens=100, overlap_tokens=15
        )
        # With 4 blocks and low max_tokens several flushes should occur;
        # the last chunk must have content
        assert chunks[-1].text.strip(), "Final chunk is empty (overlap_tail lost)"


# ---------------------------------------------------------------------------
# assert_contiguous
# ---------------------------------------------------------------------------


class TestAssertContiguous:
    def test_empty_passes(self):
        assert_contiguous([])

    def test_single_chunk_passes(self):
        assert_contiguous([{"start_offset": 0, "end_offset": 100}])

    def test_valid_contiguous_chunks_pass(self):
        chunks = [
            {"start_offset": 0, "end_offset": 100},
            {"start_offset": 100, "end_offset": 200},
            {"start_offset": 250, "end_offset": 350},
        ]
        assert_contiguous(chunks)

    def test_overlapping_chunks_raise(self):
        chunks = [
            {"start_offset": 0, "end_offset": 150},
            {"start_offset": 100, "end_offset": 200},
        ]
        with pytest.raises(ValueError, match="overlap"):
            assert_contiguous(chunks)

    def test_inverted_interval_raises(self):
        chunks = [{"start_offset": 200, "end_offset": 100}]
        with pytest.raises(ValueError, match="inverted"):
            assert_contiguous(chunks)

    def test_allow_overlap_skips_overlap_check(self):
        chunks = [
            {"start_offset": 0, "end_offset": 150},
            {"start_offset": 100, "end_offset": 200},
        ]
        # Should NOT raise
        assert_contiguous(chunks, allow_overlap=True)
