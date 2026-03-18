"""High-level responder used by backend chat endpoints."""

import logging
import re
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
    # Collapse accidental extra spaces before punctuation.
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
    ) -> Dict[str, Any]:
        """Run the full retrieve-then-generate pipeline.

        Args:
            query: The user's natural-language question.
            top_k: Number of chunks to retrieve.
            folder_id: Optional single file-level filter (legacy).
            selected_files: Optional list of file/directory paths to restrict search.

        Returns:
            Dict with keys: answer, citations, chunks.
        """
        # Resolve selected file paths to database file IDs
        file_ids: Optional[List[int]] = None
        if selected_files is not None:
            file_ids = self.db.get_file_ids_for_paths(selected_files)
            if not file_ids:
                # User explicitly selected files but none matched — return no results
                # rather than falling back to searching everything.
                file_ids = []

        logger.info("Retrieving top-%d chunks for query: %s", top_k, query[:80])
        chunks = await self.retriever.retrieve(
            query,
            top_k=top_k,
            folder_id=folder_id,
            file_ids=file_ids,
            selected_file_paths=selected_files,
        )

        if not chunks:
            return {
                "answer": "I couldn't find any relevant documents to answer your question.",
                "citations": [],
                "chunks": [],
            }

        logger.info("Retrieved %d chunks, generating response", len(chunks))
        answer = await self.rag.generate_response(query, chunks)
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
