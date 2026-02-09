"""Unit tests for the ingestion pipeline."""

import pytest
from pathlib import Path

from ingestion import (
    parse_and_prepare,
    get_input_handler,
    TextInput,
    CodeInput,
    IngestionConfig,
)
from ingestion.models import (
    StructuredDocument,
    ContentBlock,
    BlockType,
    SourceModality,
    ExtractionMethod,
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
    f.write_text('def foo():\n    return 42', encoding="utf-8")

    doc = parse_and_prepare(CodeInput(), str(f), config=IngestionConfig())
    assert doc.source_modality == SourceModality.CODE
    assert len(doc.blocks) == 1
    assert doc.blocks[0].block_type == BlockType.CODE_BLOCK
    assert "def foo" in doc.blocks[0].content


def test_get_input_handler_selects_by_extension() -> None:
    """get_input_handler selects correct handler by extension."""
    assert type(get_input_handler("x.pdf")).__name__ == "PDFInput"
    assert type(get_input_handler("x.png")).__name__ == "ImageInput"
    assert type(get_input_handler("x.py")).__name__ == "CodeInput"
    assert type(get_input_handler("x.txt")).__name__ == "TextInput"


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
