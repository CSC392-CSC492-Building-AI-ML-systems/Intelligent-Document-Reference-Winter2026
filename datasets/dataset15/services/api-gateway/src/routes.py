"""API routes for api-gateway."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1")


@router.get("/status")
async def get_status():
    return {"service": "api-gateway", "version": "1.0.0"}


@router.post("/process")
async def process_request(payload: dict):
    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload")
    return {"processed": True, "service": "api-gateway"}
