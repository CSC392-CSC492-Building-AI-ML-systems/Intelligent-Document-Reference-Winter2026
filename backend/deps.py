"""FastAPI dependency helpers.

Provides a singleton AppContext that is initialized once at import time
via ``bootstrap()`` and shared across all request handlers.
"""

from core.bootstrap import bootstrap
from core.context import AppContext

_ctx: AppContext = bootstrap()


def get_context() -> AppContext:
    """Return the application-wide AppContext singleton.

    Returns:
        The bootstrapped AppContext instance.
    """
    return _ctx
