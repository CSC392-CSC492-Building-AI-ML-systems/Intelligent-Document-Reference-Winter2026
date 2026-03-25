"""Runtime model/backend configuration helpers.

Resolves persisted UI settings into concrete model client instances and applies them
onto the shared AppContext.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from model_clients.registry import ClientRegistry

_INFERENCE_BACKENDS = {"local", "api", "gemini"}
_EMBEDDING_BACKENDS = {"local", "api", "gemini", "voyage"}
logger = logging.getLogger(__name__)


def _normalize_backend(value: Any, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def _as_non_empty_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _resolve_api_keys(raw: Dict[str, Any]) -> Dict[str, Optional[str]]:
    # UI stores API keys in a generic map. Support both explicit provider keys
    # and legacy model-name keys to stay backward compatible.
    key_map = raw.get("apiKeys") if isinstance(raw.get("apiKeys"), dict) else {}

    openai = _as_non_empty_str(key_map.get("openai")) or _as_non_empty_str(
        key_map.get("gpt-4")
    )
    gemini = _as_non_empty_str(key_map.get("gemini")) or _as_non_empty_str(
        key_map.get("gemini-2.5")
    )
    voyage = _as_non_empty_str(key_map.get("voyage"))

    return {
        "openai": openai,
        "gemini": gemini,
        "voyage": voyage,
    }


def resolve_runtime_preferences(ctx) -> Dict[str, Any]:
    """Resolve runtime model/backend preferences from persisted settings + defaults."""
    persisted: Dict[str, Any] = {}
    if getattr(ctx, "settings_store", None) is not None:
        persisted = ctx.settings_store.get_all() or {}

    model_provider = persisted.get("modelProvider")
    default_inference_backend = getattr(
        ctx.settings, "default_inference_backend", "api"
    )
    default_embedding_backend = getattr(
        ctx.settings, "default_embedding_backend", "gemini"
    )

    # If provider is explicitly local and no explicit backend was stored yet,
    # default both sides to local.
    inferred_inference = (
        "local" if model_provider == "local" else default_inference_backend
    )
    inferred_embedding = (
        "local" if model_provider == "local" else default_embedding_backend
    )

    inference_backend = _normalize_backend(
        persisted.get("inference_backend"), _INFERENCE_BACKENDS, inferred_inference
    )
    embedding_backend = _normalize_backend(
        persisted.get("embedding_backend"), _EMBEDDING_BACKENDS, inferred_embedding
    )

    # Keep legacy selectedModel as fallback for inference_model if present.
    inference_model = _as_non_empty_str(
        persisted.get("inference_model")
    ) or _as_non_empty_str(persisted.get("selectedModel"))
    embedding_model = _as_non_empty_str(persisted.get("embedding_model"))
    embedding_dimension_raw = persisted.get(
        "embedding_dimension", getattr(ctx.settings, "embedding_dimension", 3072)
    )
    try:
        embedding_dimension = int(embedding_dimension_raw)
    except (TypeError, ValueError):
        embedding_dimension = int(getattr(ctx.settings, "embedding_dimension", 3072))

    # Keep Gemini embeddings on fixed 3072 dimensions for operational stability.
    if embedding_backend == "gemini":
        embedding_dimension = 3072

    ollama_url = _as_non_empty_str(persisted.get("localEndpoint")) or getattr(
        ctx.settings, "ollama_url", "http://localhost:11434"
    )

    api_keys = _resolve_api_keys(persisted)

    return {
        "inference_backend": inference_backend,
        "embedding_backend": embedding_backend,
        "inference_model": inference_model,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "ollama_url": ollama_url,
        "api_keys": api_keys,
    }


def build_runtime_client(
    ctx,
    *,
    kind: str,
    prefs: Optional[Dict[str, Any]] = None,
    model_override: Optional[str] = None,
):
    """Build a model client for embedding/inference from resolved preferences."""
    effective = prefs or resolve_runtime_preferences(ctx)

    if kind == "embedding":
        backend = effective["embedding_backend"]
        model = _as_non_empty_str(model_override) or effective.get("embedding_model")
    elif kind == "inference":
        backend = effective["inference_backend"]
        model = _as_non_empty_str(model_override) or effective.get("inference_model")
    else:
        raise ValueError(f"Unsupported client kind: {kind}")

    api_key: Optional[str] = None
    if backend == "api":
        api_key = effective["api_keys"].get("openai")
    elif backend == "gemini":
        api_key = effective["api_keys"].get("gemini")
    elif backend == "voyage":
        api_key = effective["api_keys"].get("voyage")

    return ClientRegistry.get_client(
        kind,
        backend,
        model=model,
        embedding_dimension=effective.get("embedding_dimension"),
        url=effective.get("ollama_url"),
        api_key=api_key,
    )


def apply_runtime_clients(ctx) -> Dict[str, Any]:
    """Apply currently persisted backend/model configuration to AppContext."""
    prefs = resolve_runtime_preferences(ctx)

    try:
        ctx.embedding_client = build_runtime_client(ctx, kind="embedding", prefs=prefs)
    except Exception as exc:
        logger.debug(
            "Embedding client init failed with persisted settings; falling back to local defaults (%s)",
            exc,
        )
        fallback = dict(prefs)
        fallback["embedding_backend"] = "local"
        fallback["embedding_model"] = "nomic-embed-text"
        ctx.embedding_client = build_runtime_client(
            ctx, kind="embedding", prefs=fallback
        )
        prefs["embedding_backend"] = "local"
        prefs["embedding_model"] = "nomic-embed-text"

    try:
        ctx.inference_client = build_runtime_client(ctx, kind="inference", prefs=prefs)
    except Exception as exc:
        logger.debug(
            "Inference client init failed with persisted settings; falling back to local defaults (%s)",
            exc,
        )
        fallback = dict(prefs)
        fallback["inference_backend"] = "local"
        fallback["inference_model"] = "llama3"
        ctx.inference_client = build_runtime_client(
            ctx, kind="inference", prefs=fallback
        )
        prefs["inference_backend"] = "local"
        prefs["inference_model"] = "llama3"

    ctx.runtime_preferences = prefs
    return prefs
