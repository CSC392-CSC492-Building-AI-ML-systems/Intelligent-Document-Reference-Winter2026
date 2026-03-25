"""Ollama (local) client supporting embeddings and inference."""

import logging
from typing import List

import httpx

from model_clients.base import EmbeddingClient, InferenceClient

logger = logging.getLogger(__name__)


class OllamaClient(EmbeddingClient, InferenceClient):
    """HTTP client for a running Ollama instance."""

    def __init__(
        self,
        url: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        chat_model: str = "llama3",
        timeout: float = 120.0,
    ):
        self.url = url.rstrip("/")
        self.embed_model = embed_model
        self.chat_model = chat_model
        self.timeout = timeout

    # ── Embeddings ──────────────────────────────────────────────

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts via the Ollama /api/embed endpoint.

        Args:
            texts: Strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for text in texts:
            resp = httpx.post(
                f"{self.url}/api/embed",
                json={"model": self.embed_model, "input": text},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama /api/embed returns {"embeddings": [[...]]}
            embeddings.append(data["embeddings"][0])
        return embeddings

    # ── Inference / Generation ──────────────────────────────────

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a completion via the Ollama /api/generate endpoint.

        Args:
            prompt: The full prompt string.
            **kwargs: Extra params forwarded to the API (temperature, etc.).

        Returns:
            The generated text.
        """
        payload = {
            "model": kwargs.pop("model", self.chat_model),
            "prompt": prompt,
            "stream": False,
            **kwargs,
        }
        resp = httpx.post(
            f"{self.url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["response"]
