"""Resolve an authenticated RADIUS NAS to one configured Router and Site.

The caller supplies RADIUS attributes received by the internal, secret-gated
FreeRADIUS endpoint. Browser-provided router/site values are never consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from bson import ObjectId


@dataclass(frozen=True)
class NasIdentity:
    status: str
    reason: Optional[str] = None
    nas_client_id: Optional[str] = None
    nas_ip_address: Optional[str] = None
    nas_identifier: Optional[str] = None
    router_id: Optional[str] = None
    site_id: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.status == "resolved" and bool(self.router_id and self.site_id)


async def _find_rows(collection: Any, query: dict) -> list[dict]:
    cursor = collection.find(query)
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=100)
    return [row async for row in cursor]


def _id_text(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


def _object_id(value: Any) -> Optional[ObjectId]:
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def resolve_nas_identity(
    db: Any,
    nas_ip_address: Optional[str],
    nas_identifier: Optional[str],
) -> NasIdentity:
    """Resolve NAS attributes without arbitrary/first-match fallback.

    If both NAS-IP-Address and NAS-Identifier are present, each must resolve
    uniquely to the same active NAS client. Router mapping prefers the explicit
    ``Router.nas_client_id`` relationship. Legacy records may map only through
    an exact NAS IP == Router management IP match, and only when unique.
    """
    ip_value = nas_ip_address.strip() if isinstance(nas_ip_address, str) else ""
    identifier_value = nas_identifier.strip() if isinstance(nas_identifier, str) else ""
    if not ip_value and not identifier_value:
        return NasIdentity(status="unresolved", reason="missing_nas_identity")

    ip_rows = await _find_rows(db.nas_clients, {"ip_address": ip_value}) if ip_value else []
    id_rows = await _find_rows(db.nas_clients, {"nas_identifier": identifier_value}) if identifier_value else []

    if len(ip_rows) > 1 or len(id_rows) > 1:
        return NasIdentity(status="ambiguous", reason="duplicate_nas_mapping")
    if ip_value and not ip_rows:
        return NasIdentity(status="unresolved", reason="unknown_nas_ip")
    if identifier_value and not id_rows:
        return NasIdentity(status="unresolved", reason="unknown_nas_identifier")

    nas_by_ip = ip_rows[0] if ip_rows else None
    nas_by_identifier = id_rows[0] if id_rows else None
    if nas_by_ip and nas_by_identifier and nas_by_ip.get("_id") != nas_by_identifier.get("_id"):
        return NasIdentity(status="ambiguous", reason="nas_attributes_disagree")

    nas = nas_by_ip or nas_by_identifier
    nas_id = nas.get("_id")
    nas_id_text = _id_text(nas_id)
    nas_ip = nas.get("ip_address")
    nas_identifier_value = nas.get("nas_identifier")
    nas_status = str(nas.get("status") or "active").lower()
    if nas_status in {"inactive", "disabled"}:
        return NasIdentity(
            status="disabled", reason="nas_disabled", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value,
        )

    nas_oid = _object_id(nas_id)
    references = [nas_id_text]
    if nas_oid is not None:
        references.append(nas_oid)
    router_rows = await _find_rows(
        db.routers,
        {"nas_client_id": {"$in": references}},
    )

    # Legacy router records sometimes predate nas_client_id. Match only an
    # exact address and never choose the first router from a broader query.
    if not router_rows and nas_ip:
        router_rows = await _find_rows(db.routers, {"ip_address": nas_ip})

    if not router_rows:
        return NasIdentity(
            status="unresolved", reason="router_not_mapped", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value,
        )
    if len(router_rows) != 1:
        return NasIdentity(
            status="ambiguous", reason="multiple_router_mappings", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value,
        )

    router = router_rows[0]
    router_id = _id_text(router.get("_id"))
    router_status = str(router.get("status") or "unknown").lower()
    if router_status in {"disabled", "inactive"}:
        return NasIdentity(
            status="disabled", reason="router_disabled", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value, router_id=router_id,
        )

    router_site_id = _id_text(router.get("site_id"))
    nas_site_id = _id_text(nas.get("site_id"))
    if router_site_id and nas_site_id and router_site_id != nas_site_id:
        return NasIdentity(
            status="ambiguous", reason="router_nas_site_disagree", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value, router_id=router_id,
        )
    site_id = router_site_id or nas_site_id
    if not site_id:
        return NasIdentity(
            status="unresolved", reason="missing_site_mapping", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value, router_id=router_id,
        )

    site_oid = _object_id(site_id)
    site = await db.sites.find_one({"_id": site_oid}) if site_oid is not None else None
    if not site:
        return NasIdentity(
            status="unresolved", reason="unknown_site", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value,
            router_id=router_id, site_id=site_id,
        )
    site_status = str(site.get("status") or "active").lower()
    if site_status != "active":
        return NasIdentity(
            status="disabled", reason="site_not_active", nas_client_id=nas_id_text,
            nas_ip_address=nas_ip, nas_identifier=nas_identifier_value,
            router_id=router_id, site_id=site_id,
        )

    return NasIdentity(
        status="resolved", nas_client_id=nas_id_text, nas_ip_address=nas_ip,
        nas_identifier=nas_identifier_value, router_id=router_id, site_id=site_id,
    )
