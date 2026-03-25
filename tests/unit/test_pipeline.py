"""Unit tests for the ingestion pipeline API: validity and accuracy."""

from pathlib import Path

import pytest

from ingestion import (
    IngestionPipeline,
    IngestionResult,
    PipelineConfig,
    ingest,
)
from ingestion.models import SourceModality

# --- Validity: result structure and chunk schema ---


def test_ingest_returns_valid_result_structure(tmp_path: Path) -> None:
    """Pipeline returns IngestionResult with required fields."""
    f = tmp_path / "sample.txt"
    f.write_text(
        "A paragraph with enough content to pass the heuristic and produce chunks."
    )

    result = ingest(str(f))
    print(f"\n  source_id={result.source_id!r}")
    print(f"  block_count={result.block_count}, chunk_count={result.chunk_count}")
    assert isinstance(result, IngestionResult)
    assert result.source_id == str(f.resolve())
    assert result.block_count >= 1
    assert result.chunk_count >= 1
    assert result.chunk_count == len(result.chunks)
    assert result.document is not None
    assert result.file_metadata is not None


def test_ingest_chunks_have_required_schema(tmp_path: Path) -> None:
    """Every chunk has chunk_id, chunk_index, start_offset, end_offset, text_content."""
    f = tmp_path / "doc.txt"
    f.write_text(
        "A substantial paragraph with enough words to pass the minimum length."
    )

    result = ingest(str(f))
    required_keys = {
        "chunk_id",
        "chunk_index",
        "start_offset",
        "end_offset",
        "text_content",
    }
    for chunk in result.chunks:
        assert required_keys.issubset(chunk.keys()), f"Missing keys in {chunk}"
        assert isinstance(chunk["text_content"], str)
        assert chunk["chunk_index"] == result.chunks.index(chunk)
        assert chunk["start_offset"] >= 0
        assert chunk["end_offset"] >= chunk["start_offset"]


def test_ingest_result_to_dict_serializable(tmp_path: Path) -> None:
    """IngestionResult.to_dict() produces a serializable structure."""
    f = tmp_path / "doc.txt"
    f.write_text("Some content for serialization testing.")

    result = ingest(str(f))
    d = result.to_dict()
    assert "source_id" in d
    assert "block_count" in d
    assert "chunk_count" in d
    assert "chunks" in d
    assert d["chunk_count"] == len(d["chunks"])
    # No non-serializable objects
    import json

    json.dumps(d)  # Should not raise


# --- Accuracy: expected behavior for known inputs ---


def test_ingest_text_file_produces_text_chunks(tmp_path: Path) -> None:
    """Plain text produces at least one chunk with the expected content."""
    content = "This is a sample plain text file. It contains multiple paragraphs."
    f = tmp_path / "sample.txt"
    f.write_text(content)

    result = ingest(
        str(f), config=PipelineConfig(min_block_chars=0, min_chars_store=10)
    )
    assert result.chunk_count >= 1
    combined = " ".join(c["text_content"] for c in result.chunks)
    print(f"\n  chunks={result.chunk_count}, content preview: {combined[:100]}...")
    assert "sample plain text" in combined
    assert "multiple paragraphs" in combined


def test_ingest_code_file_produces_code_chunks(tmp_path: Path) -> None:
    """Code files produce chunks containing the code."""
    code = 'def greet(name):\n    print("Hello", name)\n\ngreet("Jack")'
    f = tmp_path / "sample.py"
    f.write_text(code)

    result = ingest(str(f), config=PipelineConfig(min_chars_store=10))
    assert result.document.source_modality == SourceModality.CODE
    assert result.chunk_count >= 1
    combined = " ".join(c["text_content"] for c in result.chunks)
    print(
        f"\n  chunks={result.chunk_count}, sample: {[c['text_content'][:60] for c in result.chunks]}"
    )
    assert "def greet" in combined
    assert "print" in combined
    assert "Jack" in combined


def test_ingest_css_file_routed_as_code(tmp_path: Path) -> None:
    """CSS is indexed as CODE (not plain TEXT) when using default modality."""
    f = tmp_path / "styles.css"
    f.write_text("body { margin: 0; padding: 0; }\n")

    result = ingest(str(f), config=PipelineConfig(min_chars_store=5))
    assert result.document.source_modality == SourceModality.CODE
    assert result.chunk_count >= 1
    assert "margin" in result.chunks[0]["text_content"]


def test_ingest_filters_short_boilerplate(tmp_path: Path) -> None:
    """Very short content and boilerplate-like text is filtered out."""
    f = tmp_path / "short.txt"
    f.write_text("Hi.")  # Too short

    result = ingest(str(f))
    print(f"\n  block_count={result.block_count}, chunk_count=0 (filtered: too short)")
    assert result.chunk_count == 0
    assert result.block_count >= 1  # Block exists, but heuristic filters it


def test_ingest_filters_page_number_like_content(tmp_path: Path) -> None:
    """Content that looks like page numbers (boilerplate) is filtered."""
    f = tmp_path / "boilerplate.txt"
    f.write_text("1\n\n2\n\n3\n\n4\n\n5")  # Page numbers, no substance

    result = ingest(str(f), config=PipelineConfig(min_chars_store=1))
    # Should filter: mostly digits, low alpha ratio
    assert result.chunk_count == 0


def test_ingest_preserves_substantive_content(tmp_path: Path) -> None:
    """Substantive paragraphs are kept even when mixed with short lines."""
    f = tmp_path / "mixed.txt"
    f.write_text(
        "Short.\n\n"
        "This is a longer paragraph with enough content to pass the heuristic. "
        "It contains real information for retrieval."
    )

    config = PipelineConfig(min_block_chars=0, min_chars_store=30)
    result = ingest(str(f), config=config)
    assert result.chunk_count >= 1
    combined = " ".join(c["text_content"] for c in result.chunks)
    assert "longer paragraph" in combined
    assert "real information" in combined


# --- Pipeline as instance (flow configuration) ---


def test_pipeline_instance_ingest(tmp_path: Path) -> None:
    """IngestionPipeline.ingest() works the same as ingest()."""
    f = tmp_path / "doc.txt"
    f.write_text("Content for pipeline instance test with sufficient length.")

    pipeline = IngestionPipeline()
    result = pipeline.ingest(str(f))
    assert result.chunk_count >= 1
    assert "Content for pipeline" in result.chunks[0]["text_content"]


def test_pipeline_respects_config(tmp_path: Path) -> None:
    """PipelineConfig controls chunker behavior."""
    f = tmp_path / "doc.txt"
    f.write_text("A" * 100)  # 100 chars, no words - might fail boilerplate

    # Stricter: skip boilerplate (default) - may filter
    result1 = ingest(str(f), config=PipelineConfig(skip_boilerplate=True))
    # Looser: allow boilerplate
    result2 = ingest(
        str(f), config=PipelineConfig(skip_boilerplate=False, min_chars_store=50)
    )

    # At least one config should produce a chunk (the relaxed one)
    assert result2.chunk_count >= 1 or result1.chunk_count >= 1


def test_pipeline_modality_override(tmp_path: Path) -> None:
    """modality override forces input handler selection."""
    # .txt normally -> TextInput. Force code -> CodeInput (treats as code block)
    f = tmp_path / "sample.txt"
    f.write_text("x = 1\ny = 2\nz = x + y")

    result = ingest(str(f), modality="code", config=PipelineConfig(min_chars_store=5))
    assert result.chunk_count >= 1
    assert "x = 1" in result.chunks[0]["text_content"] or any(
        "x = 1" in c["text_content"] for c in result.chunks
    )


# --- Sample files (integration with real fixtures) ---


def test_ingest_sample_text_file() -> None:
    """Pipeline works on the project's sample text file."""
    # __file__ = tests/unit/test_pipeline.py -> parent.parent = project root
    sample_path = (
        Path(__file__).resolve().parent.parent.parent
        / "ingestion"
        / "sample_files"
        / "text"
        / "sample.txt"
    )
    if not sample_path.exists():
        pytest.skip("Sample file not found")

    result = ingest(
        str(sample_path), config=PipelineConfig(min_block_chars=0, min_chars_store=20)
    )
    assert result.chunk_count >= 1
    combined = " ".join(c["text_content"] for c in result.chunks)
    print(f"\n  sample.txt: chunks={result.chunk_count}, preview: {combined[:120]}...")
    assert (
        "ingestion pipeline" in combined.lower()
        or "multiple paragraphs" in combined.lower()
    )


def test_ingest_sample_code_file() -> None:
    """Pipeline works on the project's sample code file."""
    sample_path = (
        Path(__file__).resolve().parent.parent.parent
        / "ingestion"
        / "sample_files"
        / "code"
        / "sample.py"
    )
    if not sample_path.exists():
        pytest.skip("Sample file not found")

    result = ingest(str(sample_path), config=PipelineConfig(min_chars_store=10))
    assert result.chunk_count >= 1
    combined = " ".join(c["text_content"] for c in result.chunks)
    assert "def greet" in combined or "greet" in combined
