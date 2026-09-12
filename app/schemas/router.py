"""Router (MikroTik NAS) schemas.

These are re-exported from app.models.router, which is the single source
of truth for RouterCreate/RouterUpdate/RouterResponse/RouterConnectivityResult
(some environments' app/models/__init__.py import them from the models
module directly, so they're defined there and mirrored here for callers
that prefer the schemas import path).
"""
from app.models.router import (
    RouterCreate,
    RouterUpdate,
    RouterResponse,
    RouterConnectivityResult,
)

__all__ = [
    "RouterCreate",
    "RouterUpdate",
    "RouterResponse",
    "RouterConnectivityResult",
]
