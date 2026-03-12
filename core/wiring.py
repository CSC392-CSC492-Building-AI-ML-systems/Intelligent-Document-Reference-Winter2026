"""Connect watchers, job queue, pipelines and API routes.

Responsibilities:
- wire watcher -> jobs
- wire jobs -> indexing workers
- ensure backend routes receive AppContext
"""

import logging

logger = logging.getLogger(__name__)


def wiring(ctx):
    """Validate that the AppContext has the essentials for the retrieval pipeline."""
    missing = []
    if ctx.db is None:
        missing.append("db")
    if ctx.embedding_client is None:
        missing.append("embedding_client")
    if ctx.inference_client is None:
        missing.append("inference_client")

    if missing:
        logger.warning("[core.wiring] Missing components: %s", ", ".join(missing))
    else:
        logger.info("[core.wiring] All retrieval components wired successfully")

    return ctx
