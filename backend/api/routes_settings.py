"""Settings endpoints (get/update persisted settings)."""

import asyncio
import logging
import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.deps import get_context
from core.context import AppContext
from core.runtime_config import (
    apply_runtime_clients,
    build_runtime_client,
    resolve_runtime_preferences,
)

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

# Cache external GET responses for the process lifetime.
_OLLAMA_MODELS_CACHE: dict[str, list[str]] = {}
_OLLAMA_MODELS_CACHE_LOCK = asyncio.Lock()

_EMBEDDING_DIMS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_EMBEDDING_DIMS_CACHE_LOCK = asyncio.Lock()
_EMBEDDING_DIMS_TTL_SECONDS = 60.0
_EMBEDDING_DIMS_GEMINI_TTL_SECONDS = 3600.0

# Allowed setting keys (whitelist to prevent arbitrary writes)
ALLOWED_KEYS = {
    "selectedModel",
    "modelProvider",
    "apiKeys",
    "temperature",
    "contextSize",
    "systemPrompt",
    "darkMode",
    "localEndpoint",
    "embedding_backend",
    "inference_backend",
    "embedding_model",
    "inference_model",
    "embedding_dimension",
    "top_k",
}


def _build_embedding_probe_client(
    ctx: AppContext,
    *,
    backend: str,
    model: str,
    endpoint: str | None,
    embedding_dimension: int | None = None,
):
    prefs = resolve_runtime_preferences(ctx)
    prefs["embedding_backend"] = backend
    prefs["embedding_model"] = model
    if endpoint:
        prefs["ollama_url"] = endpoint
    if embedding_dimension is not None and embedding_dimension > 0:
        prefs["embedding_dimension"] = embedding_dimension
    return build_runtime_client(ctx, kind="embedding", prefs=prefs)


def _normalize_ollama_model_name(name: str) -> str:
    return name.split(":", 1)[0].strip().lower()


async def _fetch_ollama_model_names(target_endpoint: str) -> list[str]:
    url = f"{target_endpoint.rstrip('/')}/api/tags"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

    models_raw = payload.get("models") if isinstance(payload, dict) else []
    return sorted(
        {
            str(item.get("name", "")).strip()
            for item in (models_raw or [])
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
    )


async def _get_cached_ollama_model_names(
    target_endpoint: str,
    *,
    refresh: bool = False,
) -> list[str]:
    endpoint = target_endpoint.rstrip("/")
    if not refresh:
        cached = _OLLAMA_MODELS_CACHE.get(endpoint)
        if cached is not None:
            return list(cached)

    async with _OLLAMA_MODELS_CACHE_LOCK:
        if not refresh:
            cached = _OLLAMA_MODELS_CACHE.get(endpoint)
            if cached is not None:
                return list(cached)
        models = await _fetch_ollama_model_names(endpoint)
        _OLLAMA_MODELS_CACHE[endpoint] = list(models)
        return list(models)


async def prewarm_external_get_caches(ctx: AppContext) -> None:
    """Best-effort startup prewarm for frequently used external GET endpoints."""
    if getattr(ctx, "settings_store", None) is None:
        return
    endpoint = ctx.settings_store.get("localEndpoint", None) or getattr(
        ctx.settings, "ollama_url", ""
    )
    endpoint = str(endpoint or "").strip()
    if not endpoint:
        return
    try:
        await _get_cached_ollama_model_names(endpoint, refresh=False)
    except Exception as exc:
        logger.debug("Skipping cache prewarm for Ollama models: %s", exc)


def _resolve_local_model_name(
    requested_model: str, installed_models: list[str]
) -> str | None:
    if requested_model in installed_models:
        return requested_model

    requested_base = _normalize_ollama_model_name(requested_model)
    for installed in installed_models:
        if _normalize_ollama_model_name(installed) == requested_base:
            return installed
    return None


async def _probe_local_embedding_dimension(endpoint: str, model: str) -> int:
    target = endpoint.rstrip("/")
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Preferred modern endpoint.
        try:
            response = await client.post(
                f"{target}/api/embed",
                json={"model": model, "input": ["dimension probe"]},
            )
            response.raise_for_status()
            payload = response.json()
            embeddings = (
                payload.get("embeddings") if isinstance(payload, dict) else None
            )
            if (
                isinstance(embeddings, list)
                and embeddings
                and isinstance(embeddings[0], list)
            ):
                return len(embeddings[0])
        except httpx.HTTPStatusError as exc:
            # Fall back only if endpoint is unavailable on older Ollama versions.
            if exc.response is None or exc.response.status_code != 404:
                raise

        # Legacy endpoint for older Ollama releases.
        response = await client.post(
            f"{target}/api/embeddings",
            json={"model": model, "prompt": "dimension probe"},
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload.get("embedding") if isinstance(payload, dict) else None
        if isinstance(embedding, list) and embedding:
            return len(embedding)

    raise ValueError("Unexpected Ollama embedding response payload")


async def _probe_embedding_dimension(client: Any) -> int:
    vectors = await asyncio.to_thread(client.embed_text, ["dimension probe"])
    if not isinstance(vectors, list) or not vectors:
        raise ValueError("Embedding probe returned no vectors")
    first = vectors[0]
    if not isinstance(first, list) or not first:
        raise ValueError("Embedding probe returned invalid vector payload")
    return len(first)


async def _probe_dimension_support(
    ctx: AppContext,
    *,
    backend: str,
    model: str,
    endpoint: str | None,
    default_dimension: int,
) -> tuple[bool, int | None]:
    if default_dimension <= 1:
        return False, None

    candidate = max(1, default_dimension // 2)
    if candidate == default_dimension:
        return False, None

    try:
        test_client = _build_embedding_probe_client(
            ctx,
            backend=backend,
            model=model,
            endpoint=endpoint,
            embedding_dimension=candidate,
        )
        probed_candidate = await _probe_embedding_dimension(test_client)
    except Exception:
        return False, None

    if probed_candidate == candidate:
        return True, candidate
    return False, None


def _suggest_dimensions(
    default_dimension: int, supported_probe: int | None
) -> list[int]:
    if default_dimension <= 0:
        return []

    suggestions = {default_dimension}
    half = max(1, default_dimension // 2)
    quarter = max(1, default_dimension // 4)
    suggestions.add(half)
    suggestions.add(quarter)
    if supported_probe is not None:
        suggestions.add(supported_probe)
    return sorted(suggestions)


def _embedding_dims_cache_key(backend: str, model: str, endpoint: str | None) -> str:
    normalized_endpoint = (endpoint or "").strip().rstrip("/")
    return f"{backend}|{model}|{normalized_endpoint}"


async def _get_cached_embedding_dims(cache_key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    async with _EMBEDDING_DIMS_CACHE_LOCK:
        cached = _EMBEDDING_DIMS_CACHE.get(cache_key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _EMBEDDING_DIMS_CACHE.pop(cache_key, None)
            return None
        return dict(payload)


async def _set_cached_embedding_dims(
    cache_key: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: float,
) -> None:
    expires_at = time.monotonic() + max(1.0, ttl_seconds)
    async with _EMBEDDING_DIMS_CACHE_LOCK:
        _EMBEDDING_DIMS_CACHE[cache_key] = (expires_at, dict(payload))


@router.get("/")
async def get_settings(ctx: AppContext = Depends(get_context)):
    """Return all persisted settings."""
    if ctx.settings_store is None:
        raise HTTPException(status_code=503, detail="Settings store not initialized")
    return ctx.settings_store.get_all()


@router.post("/update")
async def update_settings(
    payload: Dict[str, Any],
    ctx: AppContext = Depends(get_context),
):
    """Upsert settings from the provided key-value dict."""
    if ctx.settings_store is None:
        raise HTTPException(status_code=503, detail="Settings store not initialized")
    # Only allow known keys
    previous_dimension = ctx.settings_store.get(
        "embedding_dimension", getattr(ctx.settings, "embedding_dimension", 3072)
    )
    previous_embedding_backend = ctx.settings_store.get(
        "embedding_backend",
        getattr(ctx.settings, "default_embedding_backend", "gemini"),
    )
    previous_embedding_model = ctx.settings_store.get("embedding_model", None)

    reindex_required = False
    filtered = {k: v for k, v in payload.items() if k in ALLOWED_KEYS}
    if filtered:
        ctx.settings_store.set_many(filtered)
        if getattr(ctx, "db", None) is not None:
            resolved_prefs = resolve_runtime_preferences(ctx)
            new_backend = str(
                resolved_prefs.get("embedding_backend") or previous_embedding_backend
            )
            new_model = str(
                resolved_prefs.get("embedding_model") or previous_embedding_model or ""
            )
            endpoint = str(
                resolved_prefs.get("ollama_url")
                or getattr(ctx.settings, "ollama_url", "")
            ).strip()

            backend_changed = new_backend != previous_embedding_backend
            model_changed = new_model != previous_embedding_model

            try:
                new_dimension_raw = filtered.get(
                    "embedding_dimension", previous_dimension
                )
                new_dimension = int(new_dimension_raw)
                old_dimension = int(previous_dimension)
            except (TypeError, ValueError):
                new_dimension = None
                old_dimension = None

            target_dimension = (
                new_dimension if (new_dimension and new_dimension > 0) else None
            )

            # Keep Gemini embeddings fixed at 3072 to avoid long probe calls and
            # ensure indexing remains stable.
            if new_backend == "gemini":
                target_dimension = 3072

            # If embedding backend/model changes and no explicit dimension was provided,
            # probe the model default so DB + runtime stay in sync with real vector size.
            if (
                target_dimension is None
                and (backend_changed or model_changed)
                and new_backend != "gemini"
            ):
                try:
                    if new_backend == "local":
                        if not endpoint:
                            raise ValueError("No Ollama endpoint configured")
                        local_models = await _fetch_ollama_model_names(endpoint)
                        resolved_local_model = (
                            _resolve_local_model_name(new_model, local_models)
                            or new_model
                        )
                        target_dimension = await _probe_local_embedding_dimension(
                            endpoint=endpoint,
                            model=resolved_local_model,
                        )
                        # Persist resolved local tag (e.g. model:latest) for stability.
                        if resolved_local_model and resolved_local_model != new_model:
                            ctx.settings_store.set_many(
                                {"embedding_model": resolved_local_model}
                            )
                            new_model = resolved_local_model
                    else:
                        probe_client = _build_embedding_probe_client(
                            ctx,
                            backend=new_backend,
                            model=new_model,
                            endpoint=endpoint if new_backend == "local" else None,
                            embedding_dimension=None,
                        )
                        target_dimension = await _probe_embedding_dimension(
                            probe_client
                        )
                except Exception:
                    # Fallback without crashing settings update.
                    target_dimension = (
                        ctx.db.get_vector_dimension()
                        or old_dimension
                        or int(getattr(ctx.settings, "embedding_dimension", 3072))
                    )

            if target_dimension is None:
                target_dimension = (
                    ctx.db.get_vector_dimension()
                    or old_dimension
                    or int(getattr(ctx.settings, "embedding_dimension", 3072))
                )

            # Keep persisted setting aligned with the effective runtime dimension.
            try:
                persisted_dimension = int(
                    ctx.settings_store.get("embedding_dimension", target_dimension)
                )
            except (TypeError, ValueError):
                persisted_dimension = int(target_dimension)
            if int(target_dimension) != persisted_dimension:
                ctx.settings_store.set_many(
                    {"embedding_dimension": int(target_dimension)}
                )

            if int(target_dimension) != int(old_dimension or 0):
                ctx.db.reconfigure_vector_dimension(int(target_dimension))
                reindex_required = True
            elif backend_changed or model_changed:
                # Even with same vector size, embeddings from different models are not
                # semantically compatible. Force a clean reindex.
                ctx.db.reconfigure_vector_dimension(int(target_dimension))
                reindex_required = True

        apply_runtime_clients(ctx)
    return {
        "status": "ok",
        "settings": ctx.settings_store.get_all(),
        "runtime": getattr(ctx, "runtime_preferences", None),
        "reindex_required": reindex_required,
    }


@router.post("/reindex")
async def trigger_reindex(ctx: AppContext = Depends(get_context)):
    """Force reindex all configured files/directories.

    Automatically aligns the vector table dimension with the current
    embedding model before re-indexing so switching models never results
    in a dimension mismatch.
    """
    if ctx.settings_store is None:
        raise HTTPException(status_code=503, detail="Settings store not initialized")
    if not ctx.db:
        raise HTTPException(status_code=503, detail="Database not initialized")

    from core.runtime_config import apply_runtime_clients as _apply
    from core.runtime_config import resolve_runtime_preferences as _resolve

    _apply(ctx)

    prefs = _resolve(ctx)
    eb = prefs.get("embedding_backend", "gemini")
    em = prefs.get("embedding_model", "")
    target_dim = int(prefs.get("embedding_dimension", 3072))

    if not ctx.embedding_client:
        raise HTTPException(status_code=503, detail="Embedding client not available")

    # Probe the real output dimension from the current embedding client so
    # the vector table always matches what the model actually produces.
    try:
        probe_vecs = await asyncio.to_thread(
            ctx.embedding_client.embed_text, ["dimension probe"]
        )
        if probe_vecs and probe_vecs[0]:
            target_dim = len(probe_vecs[0])
    except Exception as exc:
        logger.warning(
            "Could not probe embedding dimension, using config value %d: %s",
            target_dim,
            exc,
        )

    # Always reconfigure: this drops stale data and ensures the vec_items
    # table AND the in-memory vector_dimension attribute both match the
    # actual embedding model output.  Safe even when dim hasn't changed
    # because reconfigure_vector_dimension unconditionally rebuilds the table.
    current_db_dim = ctx.db.get_vector_dimension()
    logger.info(
        "Reindex: reconfiguring vector table %s -> %s (backend=%s, model=%s)",
        current_db_dim,
        target_dim,
        eb,
        em,
    )
    ctx.db.reconfigure_vector_dimension(target_dim)
    if ctx.settings_store:
        ctx.settings_store.set_many({"embedding_dimension": target_dim})

    from ingestion.pipeline import run_index

    file_indexing_cfg = None
    try:
        from pathlib import Path

        import yaml

        cfg_path = Path("config/file_indexing.yaml")
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                file_indexing_cfg = yaml.safe_load(f) or {}
    except Exception:
        pass

    paths_to_index: list[str] = []
    if file_indexing_cfg:
        paths_to_index.extend(
            file_indexing_cfg.get("inclusion", {}).get("directories", [])
        )
        paths_to_index.extend(file_indexing_cfg.get("inclusion", {}).get("files", []))

    if not paths_to_index:
        return {
            "status": "ok",
            "message": "No paths configured for indexing",
            "embedding_backend": eb,
            "embedding_model": em,
            "dimension": target_dim,
            "errors": [],
        }

    def _run_all_indexing() -> tuple[int, list[str]]:
        """Synchronous helper that runs in a worker thread."""
        indexed = 0
        errs: list[str] = []
        for p in paths_to_index:
            try:
                logger.info("Reindex starting for: %s", p)
                run_index(p, ctx=ctx)
                indexed += 1
                logger.info("Reindex finished for: %s", p)
            except Exception as exc:
                logger.warning("Reindex failed for %s: %s", p, exc)
                errs.append(f"{p}: {exc}")
        return indexed, errs

    ctx.reindex_in_progress = True
    try:
        indexed_count, errors = await asyncio.to_thread(_run_all_indexing)

        return {
            "status": "ok",
            "message": f"Reindex completed for {indexed_count} paths (dim={target_dim})",
            "embedding_backend": eb,
            "embedding_model": em,
            "dimension": target_dim,
            "errors": errors[:5] if errors else [],
        }
    finally:
        ctx.reindex_in_progress = False


@router.post("/clear-indexes")
async def clear_indexes(ctx: AppContext = Depends(get_context)):
    """Clear all indexed data (chunks, vectors, files) from the database."""
    if not ctx.db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        removed = ctx.db.clear_all_indexes()
        return {
            "status": "ok",
            "message": f"Cleared all indexes. {removed} file records removed.",
            "files_removed": removed,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear indexes: {exc}")


@router.get("/ollama/models")
async def get_ollama_models(
    endpoint: str | None = None,
    refresh: bool = False,
    ctx: AppContext = Depends(get_context),
):
    """Return locally installed Ollama models from /api/tags."""
    if ctx.settings_store is None:
        raise HTTPException(status_code=503, detail="Settings store not initialized")

    saved_endpoint = ctx.settings_store.get("localEndpoint", None)
    target = (
        endpoint or saved_endpoint or getattr(ctx.settings, "ollama_url", "")
    ).strip()
    if not target:
        raise HTTPException(status_code=400, detail="No Ollama endpoint configured")

    try:
        models = await _get_cached_ollama_model_names(target, refresh=refresh)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to query Ollama at {target}: {exc}",
        )
    return {
        "endpoint": target,
        "models": models,
    }


@router.get("/embedding-dimensions")
async def get_embedding_dimensions(
    backend: str,
    model: str,
    endpoint: str | None = None,
    ctx: AppContext = Depends(get_context),
):
    """Return available embedding dimensions for a given backend/model."""
    normalized_backend = (backend or "").strip().lower()
    normalized_model = (model or "").strip()
    if not normalized_backend or not normalized_model:
        raise HTTPException(
            status_code=400,
            detail="Both backend and model are required",
        )

    if normalized_backend not in {"local", "api", "gemini", "voyage"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported embedding backend: {normalized_backend}",
        )

    saved_endpoint = (
        ctx.settings_store.get("localEndpoint", None)
        if ctx.settings_store is not None
        else None
    )
    target_endpoint = (
        endpoint or saved_endpoint or getattr(ctx.settings, "ollama_url", "")
    ).strip()

    if normalized_backend == "local" and not target_endpoint:
        raise HTTPException(status_code=400, detail="No Ollama endpoint configured")

    cache_key = _embedding_dims_cache_key(
        normalized_backend,
        normalized_model,
        target_endpoint if normalized_backend == "local" else None,
    )
    cached_payload = await _get_cached_embedding_dims(cache_key)
    if cached_payload is not None:
        return cached_payload

    if normalized_backend == "local":
        try:
            local_models = await _get_cached_ollama_model_names(target_endpoint)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to query Ollama at {target_endpoint}: {exc}",
            )

        resolved_local_model = _resolve_local_model_name(normalized_model, local_models)
        if resolved_local_model is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model '{normalized_model}' is not installed in Ollama at "
                    f"{target_endpoint}. Choose one of the scanned local models."
                ),
            )

        try:
            default_dim = await _probe_local_embedding_dimension(
                endpoint=target_endpoint,
                model=resolved_local_model,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Failed to probe local embedding model '{resolved_local_model}' at "
                    f"{target_endpoint}: {exc}"
                ),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Failed to parse embedding probe response for local model "
                    f"'{resolved_local_model}': {exc}"
                ),
            )

        response_payload = {
            "backend": normalized_backend,
            "model": resolved_local_model,
            "dimensions": [default_dim],
            "default_dimension": default_dim,
            "source": "probed",
            "configurable": False,
            "endpoint": target_endpoint,
        }
        await _set_cached_embedding_dims(
            cache_key,
            response_payload,
            ttl_seconds=_EMBEDDING_DIMS_TTL_SECONDS,
        )
        return response_payload

    if normalized_backend == "gemini":
        response_payload = {
            "backend": normalized_backend,
            "model": normalized_model,
            "dimensions": [3072],
            "default_dimension": 3072,
            "source": "static",
            "configurable": False,
            "endpoint": None,
        }
        await _set_cached_embedding_dims(
            cache_key,
            response_payload,
            ttl_seconds=_EMBEDDING_DIMS_GEMINI_TTL_SECONDS,
        )
        return JSONResponse(
            content=response_payload,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    try:
        base_client = _build_embedding_probe_client(
            ctx,
            backend=normalized_backend,
            model=normalized_model,
            endpoint=target_endpoint if normalized_backend == "local" else None,
        )
        default_dim = await _probe_embedding_dimension(base_client)
        configurable, supported_probe = await _probe_dimension_support(
            ctx,
            backend=normalized_backend,
            model=normalized_model,
            endpoint=target_endpoint if normalized_backend == "local" else None,
            default_dimension=default_dim,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to probe embedding dimensions for {normalized_backend}/{normalized_model}: {exc}",
        )

    dimensions = (
        _suggest_dimensions(default_dim, supported_probe)
        if configurable
        else [default_dim]
    )

    response_payload = {
        "backend": normalized_backend,
        "model": normalized_model,
        "dimensions": dimensions,
        "default_dimension": default_dim,
        "source": "probed",
        "configurable": configurable,
        "endpoint": target_endpoint if normalized_backend == "local" else None,
    }
    await _set_cached_embedding_dims(
        cache_key,
        response_payload,
        ttl_seconds=_EMBEDDING_DIMS_TTL_SECONDS,
    )
    return response_payload
