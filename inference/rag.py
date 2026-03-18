"""RAG prompt builder and orchestration."""

import asyncio
from typing import Any, Dict, List


class RAGProcessor:
    def __init__(self, inference_client: Any):
        self.client = inference_client

    def build_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Build a retrieval-augmented prompt with source attributions."""
        context_str = ""
        for c in chunks:
            context_str += (
                f"\n[SOURCE: {c['file_path']}]\n" f"CONTENT: {c['text_content']}\n"
            )

        return (
            "You are a professional assistant. Use the context below to answer "
            "accurately.\nEvery claim MUST cite its source path in brackets, "
            "e.g., (Source: /docs/notes.pdf).\n\n"
            f"CONTEXT:\n{context_str}\n\n"
            f"USER QUESTION: {query}\nANSWER:"
        )

    async def generate_response(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Generate an LLM response from retrieved chunks.

        Wraps the synchronous client.generate call in asyncio.to_thread
        so the event loop is not blocked.
        """
        prompt = self.build_prompt(query, chunks)
        return await asyncio.to_thread(self.client.generate, prompt)
