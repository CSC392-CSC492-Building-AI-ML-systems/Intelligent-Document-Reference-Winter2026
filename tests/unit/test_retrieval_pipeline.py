"""Unit tests for the end-to-end retrieval pipeline.

Uses lightweight mocks so no real Ollama / OpenAI / DB is needed.
"""

import sys
from unittest.mock import MagicMock

import pytest

# Provide a stub for sqlite_vec so importing db.unified doesn't fail
# when the native extension is not installed.
if "sqlite_vec" not in sys.modules:
    _sv = MagicMock()
    _sv.serialize_float32 = lambda v: b"\x00"
    sys.modules["sqlite_vec"] = _sv

from inference.citation import format_citations
from inference.rag import RAGProcessor
from inference.responder import Responder
from inference.retriever import Retriever

# ── Helpers ──────────────────────────────────────────────────────────────────

FAKE_CHUNKS = [
    {
        "id": 1,
        "text_content": "Python was created by Guido van Rossum.",
        "file_path": "/docs/python_history.md",
        "distance": 0.12,
    },
    {
        "id": 2,
        "text_content": "The first version was released in 1991.",
        "file_path": "/docs/python_history.md",
        "distance": 0.18,
    },
    {
        "id": 3,
        "text_content": "Python 3.0 was released in 2008.",
        "file_path": "/docs/python3_release.md",
        "distance": 0.25,
    },
]

FAKE_EMBEDDING = [0.1] * 1024  # Simulated 1024-dim vector


class FakeEmbeddingClient:
    """Returns a deterministic embedding vector."""

    def embed_text(self, texts):
        return [FAKE_EMBEDDING for _ in texts]


class FakeInferenceClient:
    """Returns a canned answer."""

    def generate(self, prompt, **kwargs):
        return (
            "Python was created by Guido van Rossum (Source: /docs/python_history.md)."
        )


class FakeDB:
    """Returns the pre-built FAKE_CHUNKS from search_with_metadata."""

    def search_with_metadata(
        self, query_vector, limit=5, file_id=None, file_paths=None
    ):
        return FAKE_CHUNKS[:limit]


# ── Tests ────────────────────────────────────────────────────────────────────


class TestRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_chunks(self):
        retriever = Retriever(db=FakeDB(), embedding_client=FakeEmbeddingClient())
        results = await retriever.retrieve("Who created Python?")
        assert len(results) == 3
        assert results[0]["file_path"] == "/docs/python_history.md"

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self):
        retriever = Retriever(db=FakeDB(), embedding_client=FakeEmbeddingClient())
        results = await retriever.retrieve("Who created Python?", top_k=2)
        assert len(results) == 2


class TestRAGProcessor:
    def test_build_prompt_contains_context_and_query(self):
        rag = RAGProcessor(inference_client=FakeInferenceClient())
        prompt = rag.build_prompt("Who created Python?", FAKE_CHUNKS)
        assert "Who created Python?" in prompt
        assert "/docs/python_history.md" in prompt
        assert "Guido van Rossum" in prompt

    @pytest.mark.asyncio
    async def test_generate_response_returns_string(self):
        rag = RAGProcessor(inference_client=FakeInferenceClient())
        answer = await rag.generate_response("Who created Python?", FAKE_CHUNKS)
        assert isinstance(answer, str)
        assert "Guido" in answer


class TestCitations:
    def test_format_citations_deduplicates(self):
        citations = format_citations(FAKE_CHUNKS)
        # Two unique file paths
        assert len(citations) == 2
        paths = [c["file_path"] for c in citations]
        assert "/docs/python_history.md" in paths
        assert "/docs/python3_release.md" in paths

    def test_format_citations_has_relevance(self):
        citations = format_citations(FAKE_CHUNKS)
        for c in citations:
            assert "relevance_score" in c
            assert 0.0 <= c["relevance_score"] <= 1.0

    def test_empty_chunks(self):
        assert format_citations([]) == []


class TestResponder:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """End-to-end: query → embed → retrieve → generate → citations."""
        responder = Responder(
            db=FakeDB(),
            embedding_client=FakeEmbeddingClient(),
            inference_client=FakeInferenceClient(),
        )
        result = await responder.respond("Who created Python?")
        assert "answer" in result
        assert "citations" in result
        assert "chunks" in result
        assert len(result["citations"]) == 2
        assert "Guido" in result["answer"]

    @pytest.mark.asyncio
    async def test_no_results(self):
        """When DB returns nothing, a friendly fallback is returned."""

        class EmptyDB:
            def search_with_metadata(self, *a, **kw):
                return []

        responder = Responder(
            db=EmptyDB(),
            embedding_client=FakeEmbeddingClient(),
            inference_client=FakeInferenceClient(),
        )
        result = await responder.respond("something obscure")
        assert result["citations"] == []
        assert "couldn't find" in result["answer"].lower()
