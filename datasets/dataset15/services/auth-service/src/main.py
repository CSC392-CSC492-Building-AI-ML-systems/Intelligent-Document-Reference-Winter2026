"""Main entry point for auth-service."""

import uvicorn
from fastapi import FastAPI

from .config import settings
from .middleware import setup_middleware
from .routes import router

app = FastAPI(title="auth-service", version="1.0.0")
setup_middleware(app)
app.include_router(router)


@app.get("/health")
async def health():
    return {"service": "auth-service", "status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
