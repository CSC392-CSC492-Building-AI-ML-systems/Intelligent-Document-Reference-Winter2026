"""High-level responder used by backend chat endpoints."""

import logging
from typing import Any, Dict, List, Optional

from inference.citation import format_citations
from inference.rag import RAGProcessor
from inference.retriever import Retriever

logger = logging.getLogger(__name__)

_SOURCE_MARKER_RE = re.compile(
    r"\s*\((?:source|citation)s?\s*:\s*[^)]+\)",
    flags=re.IGNORECASE,
)
_PATH_LINE_RE = re.compile(r"^\s*(?:/|[A-Za-z]:\\).*$", flags=re.MULTILINE)


def _strip_inline_source_markers(text: str) -> str:
    """Remove inline source markers; citations are returned separately."""
    cleaned = _SOURCE_MARKER_RE.sub("", text or "")
    cleaned = _PATH_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class Responder:
    """Orchestrates retrieval and generation for a user query."""

    def __init__(self, db, embedding_client, inference_client):
        self.db = db
        self.retriever = Retriever(db=db, embedding_client=embedding_client)
        self.rag = RAGProcessor(inference_client=inference_client)

    async def respond(
        self,
        query: str,
        *,
        top_k: int = 5,
        folder_id: Optional[int] = None,
        selected_files: Optional[List[str]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        context_size: Optional[int] = None,
        system_prompt: Optional[str] = None,
        inference_backend: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full retrieve-then-generate pipeline."""
        file_ids: Optional[List[int]] = None
        if selected_files is not None:
            file_ids = self.db.get_file_ids_for_paths(selected_files)
            if not file_ids:
                file_ids = []

        logger.info("Retrieving top-%d chunks for query: %s", top_k, query[:80])
        chunks = await self.retriever.retrieve(
            query, top_k=top_k, folder_id=folder_id, file_ids=file_ids
        )

        if not chunks:
            return {
                "answer": "I couldn't find any relevant documents to answer your question.",
                "citations": [],
                "chunks": [],
            }

        logger.info("Retrieved %d chunks, generating response", len(chunks))
        generate_kwargs: Dict[str, Any] = {}
        if model:
            generate_kwargs["model"] = model
        if temperature is not None:
            generate_kwargs["temperature"] = temperature
        if system_prompt is not None:
            generate_kwargs["system_prompt"] = system_prompt

        if (inference_backend or "").lower() == "local":
            effective_ctx = context_size or 4096
            generate_kwargs.setdefault("num_ctx", effective_ctx)
            generate_kwargs.setdefault("num_predict", 384)
            generate_kwargs.setdefault("keep_alive", "30m")
            generate_kwargs.setdefault(
                "max_context_chars",
                max(6000, min(effective_ctx * 3, 24000)),
            )
            generate_kwargs.setdefault("max_chunk_chars", 1800)

        answer = await self.rag.generate_response(query, chunks, **generate_kwargs)
        answer = _strip_inline_source_markers(answer)
        citations = format_citations(chunks, max_items=3, query=query)

        return {
            "answer": answer,
            "citations": citations,
            "chunks": chunks,
        }


async def respond(query: str, ctx=None, **kwargs) -> Dict[str, Any]:
    """Convenience function that builds a Responder from AppContext and runs it."""
    if ctx is None:
        raise ValueError("AppContext is required")
    responder = Responder(
        db=ctx.db,
        embedding_client=ctx.embedding_client,
        inference_client=ctx.inference_client,
    )
    return await responder.respond(query, **kwargs)
