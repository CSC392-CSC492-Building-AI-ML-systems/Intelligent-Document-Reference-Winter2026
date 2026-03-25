"""Client registry / factory.

Resolves embedding and inference clients based on the configured backend.
Backend values: "local" (Ollama), "api" (OpenAI), "gemini" (Google Gemini), "voyage" (Voyage AI).
"""

import logging

from config.settings import load_settings
from model_clients.google_client import GoogleEmbeddingClient, GoogleInferenceClient
from model_clients.ollama_client import OllamaClient
from model_clients.openai_client import OpenAIEmbeddingClient, OpenAIInferenceClient
from model_clients.voyage_client import VoyageEmbeddingClient

logger = logging.getLogger(__name__)


class ClientRegistry:
    @staticmethod
    def get_client(
        kind: str,
        backend: str,
        *,
        model: str | None = None,
        embedding_dimension: int | None = None,
        url: str | None = None,
        api_key: str | None = None,
    ):
        """Return an embedding or inference client for the given backend.

        Args:
            kind: "embedding" or "inference".
            backend: "local", "api", "gemini", or "voyage".
        """
        settings = load_settings()

        if backend == "local":
            if kind == "embedding":
                return OllamaClient(
                    url=url or settings.ollama_url,
                    embed_model=model or "nomic-embed-text",
                )
            if kind == "inference":
                return OllamaClient(
                    url=url or settings.ollama_url,
                    chat_model=model or "llama3",
                )
            raise ValueError(f"Unknown client kind '{kind}' for local backend")

        if backend == "api":
            resolved_api_key = api_key or settings.openai_api_key
            if kind == "embedding":
                return OpenAIEmbeddingClient(
                    api_key=resolved_api_key or None,
                    model=model or "text-embedding-3-small",
                    dimensions=embedding_dimension,
                )
            if kind == "inference":
                return OpenAIInferenceClient(
                    api_key=resolved_api_key or None,
                    model=model or "gpt-4o",
                )
            raise ValueError(f"Unknown client kind '{kind}' for api backend")

        if backend == "gemini":
            resolved_api_key = api_key or settings.gemini_api_key
            if kind == "embedding":
                dim = (
                    embedding_dimension
                    if embedding_dimension and embedding_dimension > 0
                    else 3072
                )
                return GoogleEmbeddingClient(
                    api_key=resolved_api_key or None,
                    model=model or "models/gemini-embedding-001",
                    output_dimensionality=dim,
                )
            if kind == "inference":
                return GoogleInferenceClient(
                    api_key=resolved_api_key or None,
                    model=model or "gemini-2.5-flash-lite",
                )
            raise ValueError(f"Unknown client kind '{kind}' for gemini backend")

        if backend == "voyage":
            if kind == "embedding":
                return VoyageEmbeddingClient(
                    api_key=api_key or settings.voyage_api_key or None,
                    model=model or "voyage-multimodal-3.5",
                )
            raise ValueError(f"Voyage backend only supports embedding, not {kind}")

        raise ValueError(
            f"Unknown backend '{backend}'. Use 'local', 'api', 'gemini', or 'voyage'."
        )
