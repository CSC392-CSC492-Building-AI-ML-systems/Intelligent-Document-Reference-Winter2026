"""Tests for document model."""

from app.models.document import Document


def test_word_count():
    doc = Document(id="1", content="hello world foo bar", source="test")
    assert doc.word_count == 4


def test_default_metadata():
    doc = Document(id="2", content="test", source="test")
    assert doc.metadata == {}
