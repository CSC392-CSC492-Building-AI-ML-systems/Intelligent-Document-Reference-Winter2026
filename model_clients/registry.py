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
    def get_client(kind: str, backend: str):
        """Return an embedding or inference client for the given backend.

        Args:
            kind: "embedding" or "inference".
            backend: "local", "api", "gemini", or "voyage".
        """
        settings = load_settings()

        if backend == "local":
            return OllamaClient(url=settings.ollama_url)

        if backend == "api":
            api_key = settings.openai_api_key
            if kind == "embedding":
                return OpenAIEmbeddingClient(api_key=api_key or None)
            if kind == "inference":
                return OpenAIInferenceClient(api_key=api_key or None)
            raise ValueError(f"Unknown client kind '{kind}' for api backend")

        if backend == "gemini":
            api_key = settings.gemini_api_key
            if kind == "embedding":
                return GoogleEmbeddingClient(api_key=api_key or None)
            if kind == "inference":
                return GoogleInferenceClient(api_key=api_key or None)
            raise ValueError(f"Unknown client kind '{kind}' for gemini backend")

        if backend == "voyage":
            if kind == "embedding":
                return VoyageEmbeddingClient(api_key=settings.voyage_api_key or None)
            raise ValueError(f"Voyage backend only supports embedding, not {kind}")

        raise ValueError(
            f"Unknown backend '{backend}'. Use 'local', 'api', 'gemini', or 'voyage'."
        )
