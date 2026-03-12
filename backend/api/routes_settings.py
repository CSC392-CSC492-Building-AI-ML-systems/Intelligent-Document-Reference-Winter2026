"""Settings endpoints (get/update persisted settings)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import get_context
from core.context import AppContext

router = APIRouter(prefix="/settings", tags=["settings"])

# Allowed setting keys (whitelist to prevent arbitrary writes)
ALLOWED_KEYS = {
    "selectedModel",
    "modelProvider",
    "apiKeys",
    "temperature",
    "contextSize",
    "systemPrompt",
    "darkMode",
    "userInfo",
    "localEndpoint",
    "embedding_backend",
    "inference_backend",
}


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
    filtered = {k: v for k, v in payload.items() if k in ALLOWED_KEYS}
    if filtered:
        ctx.settings_store.set_many(filtered)
    return {"status": "ok", "settings": ctx.settings_store.get_all()}
