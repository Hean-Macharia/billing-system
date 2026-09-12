"""MikroTik router integration - REST (RouterOS 7+) and legacy (RouterOS 6.x)."""
try:
    from app.integrations.mikrotik.legacy_client import AsyncMikroTikLegacyClient, MikroTikLegacyError
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AsyncMikroTikLegacyClient = None  # type: ignore[assignment]
    MikroTikLegacyError = RuntimeError

from app.integrations.mikrotik.rest_client import AsyncMikroTikRestClient, MikroTikRestError

__all__ = [
    "AsyncMikroTikLegacyClient",
    "MikroTikLegacyError",
    "AsyncMikroTikRestClient",
    "MikroTikRestError",
]
