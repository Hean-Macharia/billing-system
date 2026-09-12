"""Router (MikroTik) model for connectivity, health monitoring, and
RADIUS/NAS linkage.

Supports two API generations transparently:
  - api_type="rest"    RouterOS 7+, native REST API (port 443/80)
  - api_type="legacy"  RouterOS 6.x, binary API (port 8728 plaintext,
                        8729 SSL) - e.g. RB951Ui-2HnD on 6.49.21
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class RouterApiType(str, Enum):
    REST = "rest"
    LEGACY = "legacy"


class RouterStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    DISABLED = "disabled"


class Router(BaseModel):
    """A managed MikroTik router."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    name: str
    site_id: Optional[str] = None
    nas_client_id: Optional[str] = None  # link to radius nas_clients collection

    ip_address: str  # management IP
    api_type: RouterApiType = RouterApiType.LEGACY
    port: int = 8728  # 8728 legacy plaintext, 8729 legacy SSL, 443/80 for REST

    username: str
    password: str  # stored encrypted (app.core.crypto), never returned by the API
    use_ssl: bool = False
    ssl_verify: bool = False

    model_name: Optional[str] = None  # e.g. "RB951Ui-2HnD"
    routeros_version: Optional[str] = None

    wan_interface: Optional[str] = None
    lan_interface: Optional[str] = None
    pppoe_server_interface: Optional[str] = None
    hotspot_interface: Optional[str] = None
    ip_pools: List[str] = Field(default_factory=list)

    radius_server_ip: Optional[str] = None
    radius_secret: Optional[str] = None  # stored encrypted, never returned by the API

    status: RouterStatus = RouterStatus.UNKNOWN
    last_health: Optional[Dict[str, Any]] = None
    last_checked_at: Optional[datetime] = None

    location: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


LEGACY_API_PORTS = {8728, 8729}


def default_port_for(api_type: RouterApiType, use_ssl: bool) -> int:
    if api_type == RouterApiType.LEGACY:
        return 8729 if use_ssl else 8728
    return 443 if use_ssl else 80


# ---------------------------------------------------------------------- #
# Backward/alternate-naming compatibility aliases.
#
# An earlier iteration of this codebase's app/models/__init__.py imports:
#   from .router import Router, RouterInDB, RouterStatus, RouterOSVersion,
#                        RouterCreate, RouterUpdate, RouterResponse
#
# RouterOSVersion and RouterInDB never diverged in behavior from
# RouterApiType and Router respectively - they're the same concept under a
# different name (RouterOSVersion.LEGACY == RouterOS 6.x, .REST == RouterOS
# 7+; RouterInDB is just Router once persisted, which is the only form this
# model ever takes). Aliasing them here keeps both import spellings working
# without maintaining two copies of the same class.
# ---------------------------------------------------------------------- #
RouterOSVersion = RouterApiType
RouterInDB = Router


class RouterCreate(BaseModel):
    """Payload to register a new router. Also importable from app.schemas.router."""
    name: str = Field(..., min_length=1, max_length=100)
    site_id: Optional[str] = None
    nas_client_id: Optional[str] = None

    ip_address: str
    api_type: RouterApiType = RouterApiType.LEGACY
    port: Optional[int] = Field(default=None, gt=0, lt=65536)

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    use_ssl: bool = False
    ssl_verify: bool = False

    model_name: Optional[str] = None

    wan_interface: Optional[str] = None
    lan_interface: Optional[str] = None
    pppoe_server_interface: Optional[str] = None
    hotspot_interface: Optional[str] = None
    ip_pools: List[str] = Field(default_factory=list)

    radius_server_ip: Optional[str] = None
    radius_secret: Optional[str] = None

    location: Optional[str] = None
    notes: Optional[str] = None


class RouterUpdate(BaseModel):
    """Partial-update payload. Also importable from app.schemas.router."""
    name: Optional[str] = None
    site_id: Optional[str] = None
    nas_client_id: Optional[str] = None
    ip_address: Optional[str] = None
    api_type: Optional[RouterApiType] = None
    port: Optional[int] = Field(default=None, gt=0, lt=65536)
    username: Optional[str] = None
    password: Optional[str] = None
    use_ssl: Optional[bool] = None
    ssl_verify: Optional[bool] = None
    model_name: Optional[str] = None
    wan_interface: Optional[str] = None
    lan_interface: Optional[str] = None
    pppoe_server_interface: Optional[str] = None
    hotspot_interface: Optional[str] = None
    ip_pools: Optional[List[str]] = None
    radius_server_ip: Optional[str] = None
    radius_secret: Optional[str] = None
    status: Optional[RouterStatus] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class RouterResponse(BaseModel):
    """API response shape (password/radius_secret deliberately excluded).
    Also importable from app.schemas.router."""
    id: str = Field(alias="_id")
    name: str
    site_id: Optional[str] = None
    nas_client_id: Optional[str] = None
    ip_address: str
    api_type: str
    port: int
    username: str
    use_ssl: bool
    ssl_verify: bool
    model_name: Optional[str] = None
    routeros_version: Optional[str] = None
    wan_interface: Optional[str] = None
    lan_interface: Optional[str] = None
    pppoe_server_interface: Optional[str] = None
    hotspot_interface: Optional[str] = None
    ip_pools: List[str] = Field(default_factory=list)
    radius_server_ip: Optional[str] = None
    status: str
    last_health: Optional[Dict[str, Any]] = None
    last_checked_at: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RouterConnectivityResult(BaseModel):
    router_id: str
    reachable: bool
    api_type: str
    error: Optional[str] = None
    checked_at: datetime
