"""Chat / inference endpoints."""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.deps import get_context
from core.context import AppContext
from inference.responder import Responder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class QueryRequest(BaseModel):
    query: str
    model: Optional[str] = None
    mode: Optional[str] = "retrieval"
    selected_files: Optional[List[str]] = None
    temperature: Optional[float] = 0.7
    context_size: Optional[int] = 4096
    top_k: Optional[int] = 5


@router.get("/status")
async def status(ctx: AppContext = Depends(get_context)):
    """Health check: report whether the RAG pipeline is ready and how many files/chunks are indexed."""
    ready = bool(ctx.db and ctx.embedding_client and ctx.inference_client)
    indexed_files = 0
    indexed_chunks = 0
    if ctx.db:
        try:
            conn = ctx.db._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM files WHERE status='indexed'"
                ).fetchone()
                indexed_files = row["cnt"] if row else 0
                row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
                indexed_chunks = row["cnt"] if row else 0
            finally:
                conn.close()
        except Exception:
            pass
    return {
        "ready": ready,
        "indexed_files": indexed_files,
        "indexed_chunks": indexed_chunks,
        "embedding_backend": (
            ctx.settings.default_embedding_backend if ctx.settings else None
        ),
        "inference_backend": (
            ctx.settings.default_inference_backend if ctx.settings else None
        ),
    }


@router.post("/query")
async def query(request: QueryRequest, ctx: AppContext = Depends(get_context)):
    """Process a chat query through the RAG pipeline.

    1. Embed the query using the configured embedding client.
    2. Retrieve the top-k most relevant chunks from the vector store.
    3. Feed the chunks + query into the LLM to produce a cited answer.
    """
    if not ctx.db:
        raise HTTPException(status_code=503, detail="Database not initialised")
    if not ctx.embedding_client:
        raise HTTPException(status_code=503, detail="Embedding client not available")
    if not ctx.inference_client:
        raise HTTPException(status_code=503, detail="Inference client not available")

    try:
        responder = Responder(
            db=ctx.db,
            embedding_client=ctx.embedding_client,
            inference_client=ctx.inference_client,
        )
        start_time = time.monotonic()
        result = await responder.respond(
            query=request.query,
            top_k=request.top_k or 5,
            selected_files=request.selected_files,
        )
        processing_time_ms = round((time.monotonic() - start_time) * 1000)
    except Exception:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail="Error processing query")

    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "model": request.model,
        "mode": request.mode,
        "processing_time_ms": processing_time_ms,
    }
