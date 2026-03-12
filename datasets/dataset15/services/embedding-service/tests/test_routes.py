"""Route tests for embedding-service."""

import pytest
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "embedding-service"


@pytest.mark.asyncio
async def test_status():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/status")
        assert resp.status_code == 200
