"""Ollama (local) client supporting embeddings and inference."""

import base64
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, List, Union

import httpx

from model_clients.base import EmbeddingClient, InferenceClient

logger = logging.getLogger(__name__)


class OllamaClient(EmbeddingClient, InferenceClient):
    """HTTP client for a running Ollama instance.

    Thread-safe: each thread gets its own httpx.Client via threading.local()
    so the pipeline's ThreadPoolExecutor can embed files concurrently.
    """

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
        self._local = threading.local()
        self._vision_support_cache: dict[str, bool] = {}
        self._resolved_embed_model: str | None = None
        self._resolve_lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        """Return a per-thread httpx.Client (httpx.Client is NOT thread-safe)."""
        client = getattr(self._local, "client", None)
        if client is None:
            client = httpx.Client(timeout=self.timeout)
            self._local.client = client
        return client

    def close(self) -> None:
        """Close the current thread's HTTP client."""
        client = getattr(self._local, "client", None)
        if client is not None:
            client.close()
            self._local.client = None

    def supports_image_input(self, model: str | None = None) -> bool:
        """Return True when the given Ollama model appears to support image input."""
        target_model = model or self.chat_model
        if target_model in self._vision_support_cache:
            return self._vision_support_cache[target_model]

        # Fast heuristic fallback for common local VLM names.
        lowered = target_model.lower()
        heuristic = any(
            token in lowered
            for token in ("vl", "vision", "llava", "bakllava", "qwen2.5vl")
        )

        try:
            resp = self._get_client().post(
                f"{self.url}/api/show",
                json={"name": target_model},
            )
            resp.raise_for_status()
            payload = resp.json()
            capabilities = payload.get("capabilities", [])
            if isinstance(capabilities, list):
                supports = any(str(c).lower() == "vision" for c in capabilities)
                self._vision_support_cache[target_model] = supports
                return supports
        except Exception:
            # Fallback to heuristic when show endpoint or payload is unavailable.
            pass

        self._vision_support_cache[target_model] = heuristic
        return heuristic

    # ── Embeddings ──────────────────────────────────────────────

    def _resolve_embed_model_name(self) -> str:
        """Return an installed embedding model name when available."""
        with self._resolve_lock:
            return self._resolve_embed_model_locked()

    def _resolve_embed_model_locked(self) -> str:
        if self._resolved_embed_model:
            return self._resolved_embed_model

        requested = (self.embed_model or "").strip()
        if not requested:
            requested = "nomic-embed-text"

        try:
            resp = self._get_client().get(f"{self.url}/api/tags", timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            names = [
                str(item.get("name", "")).strip()
                for item in models
                if isinstance(item, dict) and str(item.get("name", "")).strip()
            ]

            if requested in names:
                self._resolved_embed_model = requested
                return requested

            requested_base = requested.split(":", 1)[0].lower()
            for name in names:
                if name.split(":", 1)[0].lower() == requested_base:
                    self._resolved_embed_model = name
                    return name

            hints = (
                "embed",
                "embedding",
                "nomic",
                "bge",
                "e5",
                "jina",
                "mxbai",
                "gte",
                "snowflake",
            )
            for name in names:
                lowered = name.lower()
                if any(h in lowered for h in hints):
                    logger.warning(
                        "Configured Ollama embedding model '%s' not found; using installed model '%s'",
                        requested,
                        name,
                    )
                    self._resolved_embed_model = name
                    return name
        except Exception:
            # Fall back to configured/default model if tag discovery fails.
            pass

        self._resolved_embed_model = requested
        return requested

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts via Ollama embedding endpoints.

        Args:
            texts: Strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        configured_batch = int(os.getenv("OLLAMA_EMBED_BATCH_SIZE", "16"))
        batch_size = max(1, configured_batch)
        max_retries = max(0, int(os.getenv("OLLAMA_EMBED_RETRIES", "2")))
        request_timeout = float(os.getenv("OLLAMA_EMBED_TIMEOUT_S", str(self.timeout)))

        def _embed_batch_legacy(batch: List[str]) -> List[List[float]]:
            """Fallback for older Ollama versions exposing only /api/embeddings."""
            vectors: List[List[float]] = []
            model_name = self._resolve_embed_model_name()
            client = self._get_client()
            for text in batch:
                resp = client.post(
                    f"{self.url}/api/embeddings",
                    json={"model": model_name, "prompt": text},
                    timeout=request_timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
                vec = payload.get("embedding")
                if not isinstance(vec, list):
                    raise ValueError(
                        "Unexpected Ollama /api/embeddings response format"
                    )
                vectors.append(vec)
            return vectors

        def _embed_batch(batch: List[str], retries_left: int) -> List[List[float]]:
            try:
                model_name = self._resolve_embed_model_name()
                resp = self._get_client().post(
                    f"{self.url}/api/embed",
                    json={"model": model_name, "input": batch},
                    timeout=request_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if not isinstance(embeddings, list):
                    raise ValueError("Unexpected Ollama embed response format")
                if len(embeddings) != len(batch):
                    raise ValueError(
                        "Unexpected Ollama embed response count: "
                        f"expected {len(batch)}, got {len(embeddings)}"
                    )
                return embeddings
            except httpx.HTTPStatusError as exc:
                # Older Ollama versions may not expose /api/embed and only support
                # /api/embeddings (single input per request).
                if exc.response is not None and exc.response.status_code == 404:
                    logger.info(
                        "Ollama /api/embed returned 404; falling back to legacy /api/embeddings"
                    )
                    return _embed_batch_legacy(batch)
                raise
            except (httpx.TimeoutException, httpx.ReadTimeout) as exc:
                # For heavy/long batches, back off to smaller requests before failing.
                if len(batch) > 1:
                    mid = len(batch) // 2
                    logger.warning(
                        "Ollama embedding timeout for batch=%d; splitting into %d and %d",
                        len(batch),
                        mid,
                        len(batch) - mid,
                    )
                    return _embed_batch(batch[:mid], retries_left) + _embed_batch(
                        batch[mid:], retries_left
                    )
                if retries_left > 0:
                    sleep_s = 0.75 * (max_retries - retries_left + 1)
                    logger.warning(
                        "Ollama embedding timeout for single input; retrying (%d left) after %.2fs",
                        retries_left,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
                    return _embed_batch(batch, retries_left - 1)
                raise exc

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_embeddings.extend(_embed_batch(batch, max_retries))
        return all_embeddings

    # ── Inference / Generation ──────────────────────────────────

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a completion via the Ollama /api/generate endpoint.

        Args:
            prompt: The full prompt string.
            **kwargs: Extra params forwarded to the API (temperature, etc.).

        Returns:
            The generated text.
        """
        options: dict[str, Any] = {}
        option_keys = {
            "temperature",
            "num_ctx",
            "num_predict",
            "top_k",
            "top_p",
            "repeat_penalty",
            "num_thread",
            "num_gpu",
        }
        for key in list(kwargs.keys()):
            if key in option_keys:
                options[key] = kwargs.pop(key)

        payload = {
            "model": kwargs.pop("model", self.chat_model),
            "prompt": prompt,
            "stream": False,
            "keep_alive": kwargs.pop("keep_alive", "30m"),
            "options": options,
            **kwargs,
        }
        resp = self._get_client().post(
            f"{self.url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    # ── Vision / Image Description ──────────────────────────────

    def _image_to_base64(self, image: Union[str, Path, bytes]) -> str:
        if isinstance(image, (str, Path)):
            data = Path(image).read_bytes()
        elif isinstance(image, bytes):
            data = image
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")
        return base64.b64encode(data).decode("utf-8")

    def describe_image(
        self,
        image: Union[str, Path, bytes],
        prompt: str | None = None,
        **kwargs,
    ) -> str:
        """Describe an image using an Ollama multimodal model.

        This enables local image-to-text extraction in ingestion when using VLMs
        such as qwen2.5vl models.
        """
        prompt_text = prompt or (
            "Describe this image in detail for search and retrieval. "
            "Extract visible text and key entities, objects, and context."
        )

        options: dict[str, Any] = {}
        option_keys = {
            "temperature",
            "num_ctx",
            "num_predict",
            "top_k",
            "top_p",
            "repeat_penalty",
            "num_thread",
            "num_gpu",
        }
        for key in list(kwargs.keys()):
            if key in option_keys:
                options[key] = kwargs.pop(key)

        payload = {
            "model": kwargs.pop("model", self.chat_model),
            "prompt": prompt_text,
            "images": [self._image_to_base64(image)],
            "stream": False,
            "keep_alive": kwargs.pop("keep_alive", "30m"),
            "options": options,
            **kwargs,
        }

        resp = self._get_client().post(
            f"{self.url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        return (resp.json().get("response") or "").strip()
