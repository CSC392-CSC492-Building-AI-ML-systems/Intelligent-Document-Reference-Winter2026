"""Embedding adapter: batch embed texts using configurable backends."""

from typing import Callable, List, Optional, Protocol


class EmbeddingClient(Protocol):
    def embed_text(self, texts: List[str]) -> List[List[float]]: ...


def _get_voyage_client() -> Optional[EmbeddingClient]:
    try:
        import os

        from model_clients.voyage_client import VoyageEmbeddingClient

        if os.getenv("VOYAGE_API_KEY"):
            return VoyageEmbeddingClient(api_key=os.getenv("VOYAGE_API_KEY"))
    except Exception:
        pass
    return None


def _get_ollama_client() -> Optional[EmbeddingClient]:
    try:
        from config.settings import load_settings
        from model_clients.ollama_client import OllamaClient

        return OllamaClient(url=load_settings().ollama_url)
    except Exception:
        pass
    return None


def embed_texts_batched(
    texts: List[str],
    *,
    client: Optional[EmbeddingClient] = None,
    batch_size: int = 32,
) -> List[List[float]]:
    """Embed texts in batches. Uses provided client or auto-detects Voyage/Ollama."""
    if not texts:
        return []
    if client is None:
        client = _get_voyage_client() or _get_ollama_client()
    if client is None:
        raise RuntimeError(
            "No embedding client available. Set VOYAGE_API_KEY or configure Ollama, "
            "or pass a custom client."
        )
    result: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        result.extend(client.embed_text(texts[i : i + batch_size]))
    return result


def get_local_embedder() -> Optional[Callable[[List[str]], List[List[float]]]]:
    """Return a local embedder if sentence-transformers is available."""
    try:
        from sentence_transformers import SentenceTransformer

        _model = None

        def _embed(texts: List[str]) -> List[List[float]]:
            nonlocal _model
            if _model is None:
                _model = SentenceTransformer("all-MiniLM-L6-v2")
            return _model.encode(texts, convert_to_numpy=True).tolist()

        return _embed
    except ImportError:
        return None
