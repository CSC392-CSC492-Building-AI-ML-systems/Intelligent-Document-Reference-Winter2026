"""FastAPI app entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import (
    routes_chat,
    routes_files,
    routes_jobs,
    routes_mini,
    routes_settings,
    routes_watcher,
)
from backend.deps import get_context
from ingestion.pipeline import run_index
from jobs import Worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start the job worker and file watcher on startup; stop on shutdown."""
    ctx = get_context()
    worker = None

    if ctx and ctx.job_queue:
        poll_interval = getattr(ctx.settings, "worker_poll_interval", 2.0)
        worker = Worker(
            queue=ctx.job_queue,
            processor=run_index,
            ctx=ctx,
            poll_interval=poll_interval,
        )
        await worker.start()
        logger.info("Job worker started via lifespan")

    if ctx and ctx.watcher:
        ctx.watcher.start_background()
        logger.info("File watcher started via lifespan")

    if ctx:
        asyncio.create_task(routes_settings.prewarm_external_get_caches(ctx))
        logger.info("Settings external GET cache prewarm scheduled")

    yield

    if ctx and ctx.watcher:
        ctx.watcher.stop()
        logger.info("File watcher stopped via lifespan")

    if worker:
        await worker.stop()
        logger.info("Job worker stopped via lifespan")


app = FastAPI(title="local-rag-backend", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers (must be before static files)
app.include_router(routes_chat.router)
app.include_router(routes_files.router)
app.include_router(routes_jobs.router)
app.include_router(routes_mini.router)
app.include_router(routes_settings.router)
app.include_router(routes_watcher.router)

# Serve static files from the frontend build
# Note: API routes are registered above, so they take precedence
ui_dist_path = Path(__file__).parent.parent / "ui" / "dist"
if ui_dist_path.exists():
    # Mount static assets (JS, CSS, etc.)
    app.mount(
        "/assets", StaticFiles(directory=str(ui_dist_path / "assets")), name="assets"
    )

    # Serve index.html for all non-API routes (SPA routing)
    # This must be registered last to catch all unmatched routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str, request: Request):
        # Check if this is an API route (should have been handled above)
        # If it's a file with extension, try to serve it
        if "." in full_path and not full_path.startswith(
            ("api/", "chat/", "files/", "jobs/", "settings/")
        ):
            file_path = ui_dist_path / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))

        # For all other routes (including /chat, /settings, etc.), serve index.html
        # No-cache so browser always gets fresh HTML after rebuilds (avoids 404 on hashed JS/CSS)
        index_path = ui_dist_path / "index.html"
        if index_path.exists():
            return FileResponse(
                str(index_path),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return {"detail": "Frontend not built"}
