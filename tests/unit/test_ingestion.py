"""Unit tests for the ingestion pipeline."""

from pathlib import Path

import pytest

from ingestion import (
    AudioInput,
    CodeInput,
    IngestionConfig,
    TextInput,
    get_input_handler,
    parse_and_prepare,
)
from ingestion.code_syntax import CodeSyntaxError
from ingestion.models import (
    BlockType,
    ContentBlock,
    ExtractionMethod,
    SourceModality,
    StructuredDocument,
)


def test_text_input_parses_file(tmp_path: Path) -> None:
    """TextInput parses plain text files."""
    f = tmp_path / "test.txt"
    f.write_text("Hello, world.\n\nSecond paragraph.", encoding="utf-8")

    doc = parse_and_prepare(TextInput(), str(f), config=IngestionConfig())
    assert isinstance(doc, StructuredDocument)
    assert doc.source_modality == SourceModality.TEXT
    assert len(doc.blocks) == 1
    assert doc.blocks[0].content == "Hello, world.\n\nSecond paragraph."
    assert doc.blocks[0].block_type == BlockType.PARAGRAPH
    assert doc.blocks[0].metadata.extraction_method == ExtractionMethod.NATIVE


def test_code_input_parses_file(tmp_path: Path) -> None:
    """CodeInput parses code files."""
    f = tmp_path / "test.py"
    f.write_text("def foo():\n    return 42", encoding="utf-8")

    doc = parse_and_prepare(CodeInput(), str(f), config=IngestionConfig())
    assert doc.source_modality == SourceModality.CODE
    assert len(doc.blocks) == 1
    assert doc.blocks[0].block_type == BlockType.CODE_BLOCK
    assert "def foo" in doc.blocks[0].content


def test_get_input_handler_selects_by_extension() -> None:
    """get_input_handler selects correct handler by extension."""
    assert type(get_input_handler("x.pdf")).__name__ == "PDFInput"
    assert type(get_input_handler("x.png")).__name__ == "ImageInput"
    assert type(get_input_handler("x.mp3")).__name__ == "AudioInput"
    assert type(get_input_handler("x.wav")).__name__ == "AudioInput"
    assert type(get_input_handler("x.py")).__name__ == "CodeInput"
    assert type(get_input_handler("x.txt")).__name__ == "TextInput"
    assert type(get_input_handler("x.md")).__name__ == "TextInput"
    assert type(get_input_handler("x.rst")).__name__ == "TextInput"


def test_code_input_rejects_invalid_python(tmp_path: Path) -> None:
    """CodeInput raises CodeSyntaxError for invalid Python."""
    f = tmp_path / "bad.py"
    f.write_text("def broken(\n", encoding="utf-8")
    with pytest.raises(CodeSyntaxError, match="Python syntax error"):
        parse_and_prepare(CodeInput(), str(f), config=IngestionConfig())


def test_code_input_rejects_invalid_json(tmp_path: Path) -> None:
    """CodeInput raises CodeSyntaxError for invalid JSON."""
    f = tmp_path / "bad.json"
    f.write_text("{ not json ", encoding="utf-8")
    with pytest.raises(CodeSyntaxError, match="JSON parse error"):
        parse_and_prepare(CodeInput(), str(f), config=IngestionConfig())


def test_code_input_rejects_invalid_css(tmp_path: Path) -> None:
    """CodeInput raises CodeSyntaxError for invalid CSS."""
    f = tmp_path / "bad.css"
    # tinycss2 reports an error token for this malformed input
    f.write_text("###", encoding="utf-8")
    with pytest.raises(CodeSyntaxError, match="CSS parse error"):
        parse_and_prepare(CodeInput(), str(f), config=IngestionConfig())


def test_audio_input_transcribes_mp3(tmp_path: Path) -> None:
    """AudioInput transcribes MP3 files when the inference client supports audio."""

    class _DummyInferenceClient:
        def transcribe_audio(self, audio):
            assert isinstance(audio, str)
            return "hello from audio"

    f = tmp_path / "clip.mp3"
    # Parser only needs a readable file path; content is not decoded directly.
    f.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00")

    doc = parse_and_prepare(
        AudioInput(),
        str(f),
        config=IngestionConfig(),
        llm_client=_DummyInferenceClient(),
    )

    assert doc.source_modality == SourceModality.AUDIO
    assert len(doc.blocks) == 1
    assert doc.blocks[0].content == "hello from audio"
    assert doc.blocks[0].block_type == BlockType.PARAGRAPH
    assert doc.blocks[0].metadata.extraction_method == ExtractionMethod.LLM_ASSISTED


def test_preprocessing_normalizes_whitespace() -> None:
    """Preprocessing normalizes whitespace in blocks."""
    from ingestion.preprocessing import preprocess

    doc = StructuredDocument(
        source_id="test",
        blocks=[
            ContentBlock(
                content="  hello   world  \n\n  foo  ",
                block_type=BlockType.PARAGRAPH,
                source_modality=SourceModality.TEXT,
            )
        ],
        source_modality=SourceModality.TEXT,
    )
    result = preprocess(doc)
    assert len(result.blocks) == 1
    assert result.blocks[0].content == "hello world\n\nfoo"


def test_structured_document_serializable() -> None:
    """StructuredDocument can be serialized to dict."""
    doc = StructuredDocument(
        source_id="test",
        blocks=[
            ContentBlock(
                content="hello",
                block_type=BlockType.PARAGRAPH,
                source_modality=SourceModality.TEXT,
            )
        ],
        source_modality=SourceModality.TEXT,
    )
    d = doc.to_dict()
    assert d["source_id"] == "test"
    assert len(d["blocks"]) == 1
    assert d["blocks"][0]["content"] == "hello"


def test_chunk_document_produces_storeable_chunks() -> None:
    """Semantic chunker turns blocks into chunks and applies store heuristic."""
    from ingestion import chunk_document

    doc = StructuredDocument(
        source_id="test",
        blocks=[
            ContentBlock(
                content="Short.",
                block_type=BlockType.PARAGRAPH,
                source_modality=SourceModality.TEXT,
            ),
            ContentBlock(
                content="This is a longer paragraph with enough content to pass the heuristic.",
                block_type=BlockType.PARAGRAPH,
                source_modality=SourceModality.TEXT,
            ),
            ContentBlock(
                content="def foo():\n    return 42",
                block_type=BlockType.CODE_BLOCK,
                source_modality=SourceModality.CODE,
            ),
        ],
        source_modality=SourceModality.TEXT,
    )
    # Don't merge (min_block_chars > first block); lower min_chars_store so code block is kept
    chunks = chunk_document(
        doc,
        min_block_chars=100,
        max_block_chars=10_000,
        min_chars_store=10,
    )
    # Short paragraph filtered out; second paragraph and code block stored
    assert len(chunks) == 2
    assert "longer paragraph" in chunks[0]["text_content"]
    assert "def foo()" in chunks[1]["text_content"]
    assert all(
        "chunk_id" in c and "chunk_index" in c and "text_content" in c for c in chunks
    )


def test_should_store_chunk_heuristic() -> None:
    """Store heuristic filters by length and boilerplate."""
    from ingestion.chunking.semantic import CandidateChunk, should_store_chunk

    assert (
        should_store_chunk(
            CandidateChunk("Too short", (BlockType.PARAGRAPH,), 2, 0, 9),
            min_chars=30,
        )
        is False
    )
    assert (
        should_store_chunk(
            CandidateChunk(
                "A normal paragraph with enough words to pass the minimum length.",
                (BlockType.PARAGRAPH,),
                15,
                0,
                60,
            ),
            min_chars=30,
        )
        is True
    )
    assert (
        should_store_chunk(
            CandidateChunk("PAGE 1", (BlockType.PARAGRAPH,), 2, 0, 6),
            min_chars=3,
            skip_boilerplate=True,
        )
        is False
    )
