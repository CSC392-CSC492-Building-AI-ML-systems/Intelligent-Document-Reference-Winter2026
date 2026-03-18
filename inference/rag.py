"""RAG prompt builder and orchestration."""

import asyncio
from typing import Any, Dict, List


class RAGProcessor:
    def __init__(self, inference_client: Any):
        self.client = inference_client

    def build_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Build a retrieval-augmented prompt for markdown-only output."""
        context_str = ""
        for c in chunks:
            context_str += (
                f"\n[SOURCE: {c['file_path']}]\nCONTENT: {c['text_content']}\n"
            )

        return (
            "You are a professional assistant. Use the context below to answer "
            "accurately and concisely.\n"
            "Return markdown only (headings, bullet lists, tables where helpful).\n"
            "Do not append source markers in the answer text.\n"
            "Do not include absolute or relative source file paths in the answer body.\n"
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
