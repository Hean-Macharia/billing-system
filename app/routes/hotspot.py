"""HotSpot plan (profile) API routes."""
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.hotspot import HotspotPlanCreate, HotspotPlanUpdate
from app.schemas.portal import (
    HotspotDeviceAttestationRequest,
    HotspotDeviceLookupRequest,
    HotspotPurchaseRequest,
    HotspotReconnectRequest,
    HotspotTrialRequest,
)
from app.services.hotspot_attestation_service import HotspotAttestationService
from app.services.hotspot_service import HotspotService
from app.services.router_service import RouterService
from app.utils.helpers import success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/hotspot", tags=["HotSpot"])


def _correlation_id(request: Request, response: Response) -> str:
    supplied = request.headers.get("X-Correlation-ID", "")
    value = supplied.lower() if re.fullmatch(r"[A-Fa-f0-9]{32}", supplied) else uuid.uuid4().hex
    response.headers["X-Correlation-ID"] = value
    return value


def _plan_to_response(p) -> dict:
    return {
        "_id": str(p.id),
        "name": p.name,
        "site_id": p.site_id,
        "duration_hours": p.duration_hours,
        "data_allowance_mb": p.data_allowance_mb,
        "max_devices": p.max_devices,
        "rate_limit": p.rate_limit,
        "price": p.price,
        "currency": p.currency,
        "description": p.description,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _resolve_hotspot_device(data: HotspotDeviceLookupRequest, db: AsyncIOMotorDatabase) -> dict:
    """Verify all supplied client identifiers against one unique live DHCP lease."""
    import asyncio
    import ipaddress

    if not data.ip_address and not data.mac_address:
        raise ValidationError("Provide an IP address or MAC address")
    if data.ip_address:
        try:
            address = ipaddress.ip_address(data.ip_address)
        except ValueError as exc:
            raise ValidationError("Enter a valid device IP address") from exc
        if not address.is_private or address.is_loopback or address.is_link_local:
            raise ValidationError("Device lookup is limited to private LAN IP addresses")

    target_ip = str(ipaddress.ip_address(data.ip_address)) if data.ip_address else None
    target_mac = data.mac_address.replace("-", ":").upper() if data.mac_address else None
    routers = await db.routers.find(
        {"status": {"$ne": "disabled"}},
        {"_id": 1, "name": 1, "site_id": 1},
    ).to_list(length=1000)
    if not routers:
        raise ServiceUnavailableError("No MikroTik routers are configured for device verification")

    service = RouterService(db)
    unavailable_routers = []
    matches = []
    expired_matches = []

    # Keep the multi-router scan bounded while avoiding a serial relay roundtrip
    # for every configured router. A partial scan still fails closed below.
    semaphore = asyncio.Semaphore(4)

    async def fetch_router_leases(router: dict) -> tuple[dict, list]:
        router_id = str(router["_id"])
        async with semaphore:
            try:
                return router, await service.get_dhcp_leases(router_id)
            except Exception as exc:
                unavailable_routers.append(router_id)
                logger.warning(
                    "HotSpot DHCP lease lookup failed for router %s (%s)",
                    router_id,
                    type(exc).__name__,
                )
                return router, []

    router_leases = await asyncio.gather(*(fetch_router_leases(router) for router in routers))
    for router, leases in router_leases:
        router_id = str(router["_id"])
        for lease in leases:
            lease_ip = str(lease.get("address") or "")
            lease_mac = (lease.get("mac_address") or "").replace("-", ":").upper()
            if not lease_ip or not lease_mac:
                continue
            if target_ip and lease_ip != target_ip:
                continue
            if target_mac and lease_mac != target_mac:
                continue

            lease_status = str(lease.get("status") or "").lower()
            expires_seconds = lease.get("expires_seconds")
            expired = (lease_status and lease_status != "bound") or (
                expires_seconds is not None and expires_seconds <= 0
            )
            result = {
                    "verification_status": "verified",
                    "verification_method": "router_dhcp_lease",
                    "ip_address": lease_ip,
                    "mac_address": lease_mac,
                    "hostname": lease.get("hostname"),
                    "lease_status": lease_status or None,
                    "lease_expires_in_seconds": expires_seconds,
                    "router_id": router_id,
                    "router_name": router.get("name"),
                    "site_id": router.get("site_id"),
                }
            (expired_matches if expired else matches).append(result)

    # A partial scan cannot establish uniqueness across sites or overlapping LANs.
    if unavailable_routers:
        raise ServiceUnavailableError(
            "Device verification is temporarily unavailable because one or more configured routers could not be checked"
        )

    all_matches = matches + expired_matches
    matching_router_ids = {record["router_id"] for record in all_matches}
    if len(matching_router_ids) > 1:
        matching_sites = {str(record.get("site_id") or "") for record in all_matches}
        category = "multiple routers across multiple sites" if len(matching_sites) > 1 else "multiple routers at one site"
        logger.warning(
            "HotSpot DHCP lookup found matching device records on multiple routers",
            extra={
                "event": "hotspot_dhcp_lookup_ambiguous_routers",
                "router_ids": sorted(matching_router_ids),
                "site_count": len(matching_sites),
                "record_count": len(all_matches),
            },
        )
        raise ConflictError(
            f"This device matches DHCP records on {category}; ask support to resolve the router assignment"
        )

    if len(matches) > 1:
        logger.warning(
            "HotSpot DHCP lookup found duplicate active leases on one router",
            extra={
                "event": "hotspot_dhcp_lookup_duplicate_leases",
                "router_id": next(iter(matching_router_ids)),
                "record_count": len(matches),
            },
        )
        raise ConflictError("This router has duplicate active DHCP lease records for the device; ask support to resolve them")

    if matches and expired_matches:
        logger.warning(
            "HotSpot DHCP lookup found both active and expired lease records on one router",
            extra={
                "event": "hotspot_dhcp_lookup_active_expired_duplicate",
                "router_id": next(iter(matching_router_ids)),
                "record_count": len(all_matches),
            },
        )
        raise ConflictError("This router has conflicting active and expired DHCP records for the device; ask support to resolve them")
    if matches:
        return matches[0]
    if expired_matches:
        raise ConflictError("The matching MikroTik DHCP lease is no longer active. Reconnect to Wi-Fi and try again")
    raise NotFoundError("No DHCP lease matched the supplied hotspot device details")


# ── Plans ──

@router.post("/plans", response_model=dict, status_code=201)
async def create_hotspot_plan(
    request: Request,
    data: HotspotPlanCreate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.create_plan(data)
    return success_response(message="HotSpot plan created", data=_plan_to_response(plan), status_code=201)


@router.get("/plans", response_model=dict)
async def list_hotspot_plans(
    request: Request,
    site_id: Optional[str] = None,
    active_only: bool = False,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plans = await service.list_plans(site_id=site_id, active_only=active_only)
    return success_response(message="HotSpot plans retrieved", data=[_plan_to_response(p) for p in plans])


@router.get("/plans/public", response_model=dict)
async def list_public_hotspot_plans(
    request: Request,
    response: Response,
    site_id: Optional[str] = None,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Serve global plans, plus plans for a valid short-lived router context.

    ``site_id`` remains accepted for compatibility but is never trusted.
    """
    service = HotspotService(db)
    context = await HotspotAttestationService(db).get_context(hotspot_context)
    if hotspot_context:
        response.headers["Cache-Control"] = "private, no-store"
    plans = await service.list_plans(
        site_id=context.site_id if context else None,
        active_only=True,
        include_global=bool(context),
        global_only=not context,
    )
    return success_response(
        message="Available HotSpot plans",
        data=[
            {
                "_id": str(p.id),
                "site_id": p.site_id,
                "name": p.name,
                "duration_hours": p.duration_hours,
                "data_allowance_mb": p.data_allowance_mb,
                "max_devices": p.max_devices,
                "rate_limit": p.rate_limit,
                "price": p.price,
                "currency": p.currency,
                "description": p.description,
            }
            for p in plans
        ],
    )


@router.post("/devices/attest", response_model=dict)
async def attest_hotspot_device(
    request: Request,
    data: HotspotDeviceAttestationRequest,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Use untrusted RouterOS hints to request authenticated relay observation."""
    correlation_id = _correlation_id(request, response)
    context = await HotspotAttestationService(db).create_context(
        data.ip_address, data.mac_address, correlation_id=correlation_id
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return success_response(message="HotSpot device context verified", data=context)


@router.post("/devices/lookup", response_model=dict)
async def lookup_hotspot_device(data: HotspotDeviceLookupRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Resolve one private LAN IP or MAC against configured MikroTik DHCP leases."""
    device = await _resolve_hotspot_device(data, db)
    return success_response(message="Device verified against a unique active router lease", data=device)


@router.post("/purchase", response_model=dict, status_code=201)
async def purchase_hotspot_voucher(
    data: HotspotPurchaseRequest,
    response: Response,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Start a walk-up purchase after server-side device and site validation."""
    plan = await HotspotService(db).get_plan(data.plan_id)
    if not hotspot_context:
        raise ConflictError("Secure device verification is required before starting a HotSpot purchase")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    correlation_id = uuid.uuid4().hex
    response.headers["X-Correlation-ID"] = correlation_id
    trusted_context = await HotspotAttestationService(db).attest_purchase_device(
        raw_token=hotspot_context,
        device_type=data.device_type,
        client_ip=data.ip_address,
        client_mac=data.device_mac,
        correlation_id=correlation_id,
    )

    from app.services.mpesa_service import MpesaService
    service = MpesaService(db)
    tx = await service.initiate_hotspot_purchase(
        plan_id=data.plan_id,
        phone_number=data.phone_number,
        device_type=data.device_type,
        device_mac=trusted_context.client_mac,
        purchase_context_mac=(
            getattr(trusted_context, "purchase_context_mac", None)
            or trusted_context.client_mac
        ),
        purchase_context_router_id=(
            getattr(trusted_context, "purchase_context_router_id", None)
            or trusted_context.router_id
        ),
        purchase_context_site_id=(
            getattr(trusted_context, "purchase_context_site_id", None)
            or trusted_context.site_id
        ),
        trusted_site_id=trusted_context.site_id,
        trusted_router_id=trusted_context.router_id,
        idempotency_key=data.idempotency_key,
    )
    return success_response(
        message="STK push sent - check your phone",
        data={"checkout_request_id": tx.checkout_request_id},
        status_code=201,
    )


@router.get("/purchase/status/{checkout_request_id}", response_model=dict)
async def purchase_status(
    checkout_request_id: str,
    response: Response,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return checkout state only to the same short-lived trusted device context."""
    from app.services.mpesa_service import MpesaService
    correlation_id = uuid.uuid4().hex
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    service = MpesaService(db)
    tx = await service.get_by_checkout_id(checkout_request_id)
    if not hotspot_context:
        logger.info(
            "HotSpot purchase status denied",
            extra={"event": "hotspot_purchase_status_denied", "correlation_id": correlation_id, "stage": "context", "reason": "missing_context"},
        )
        raise ConflictError("Secure device context is required to check this purchase")
    trusted = await HotspotAttestationService(db).get_context(hotspot_context)
    if not trusted:
        logger.info(
            "HotSpot purchase status denied",
            extra={"event": "hotspot_purchase_status_denied", "correlation_id": correlation_id, "stage": "context", "reason": "context_expired_or_invalid"},
        )
        raise ConflictError("The trusted WiFi context is missing or expired. Reopen the WiFi sign-in page")
    normalized_mac = str(getattr(trusted, "client_mac", "")).replace("-", ":").upper()
    transaction_mac = str(getattr(tx, "device_mac", "")).replace("-", ":").upper()
    initiating_mac = str(
        getattr(tx, "purchase_context_mac", None)
        or (transaction_mac if getattr(tx, "device_type", "this_device") == "this_device" else "")
    ).replace("-", ":").upper()
    initiating_router_id = str(getattr(tx, "purchase_context_router_id", None) or tx.router_id)
    initiating_site_id = str(getattr(tx, "purchase_context_site_id", None) or tx.site_id)
    if (
        not initiating_router_id
        or not initiating_site_id
        or initiating_router_id != str(trusted.router_id)
        or initiating_site_id != str(trusted.site_id)
        or not transaction_mac
        or not initiating_mac
        or initiating_mac != normalized_mac
    ):
        logger.info(
            "HotSpot purchase status denied",
            extra={
                "event": "hotspot_purchase_status_denied",
                "correlation_id": correlation_id,
                "stage": "purchase_binding",
                "reason": "device_router_or_site_mismatch",
                "router_matches": initiating_router_id == str(trusted.router_id),
                "site_matches": initiating_site_id == str(trusted.site_id),
                "device_matches": bool(initiating_mac and initiating_mac == normalized_mac),
            },
        )
        raise ConflictError("This purchase does not belong to the currently verified WiFi device")
    # Retry a due settlement only after the caller has proved possession of
    # the trusted context bound to this purchase. This path never asks Daraja
    # again; only a callback already verified by the provider can settle.
    status_reader = getattr(service, "get_hotspot_purchase_status", service.get_by_checkout_id)
    tx = await status_reader(checkout_request_id)
    settled = (
        tx.status.value == "success"
        and tx.settled is True
        and tx.settlement_status == "completed"
        and tx.callback_received is True
        and tx.settlement_review_required is not True
    )
    voucher = None
    if settled and tx.voucher_code:
        voucher = await db.vouchers.find_one({
            "voucher_code": tx.voucher_code,
            "purchase_transaction_id": tx.id,
        }, {"expiry_date": 1})
    expires_at = voucher.get("expiry_date") if voucher else None
    return success_response(
        message="Purchase status retrieved",
        data={
            "status": tx.status.value,
            "settled": settled,
            "settlement_review_required": tx.settlement_review_required,
            "access_token": tx.mpesa_receipt_number if settled else None,
            "login_username": tx.voucher_code if settled else None,
            # Kept for compatibility with previously shipped portal builds.
            "voucher_code": tx.voucher_code if settled else None,
            "package_name": tx.account_reference if settled else None,
            "amount": tx.amount if settled else None,
            "device_type": tx.device_type,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "result_desc": tx.result_desc,
        },
    )


@router.post("/reconnect", response_model=dict)
async def reconnect_hotspot_purchase(
    data: HotspotReconnectRequest,
    response: Response,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Resolve a confirmed receipt, re-attest this device, and return its RADIUS username."""
    if not hotspot_context:
        raise ConflictError("Secure device verification is required before reconnecting")
    attestation = HotspotAttestationService(db)
    trusted = await attestation.get_context(hotspot_context)
    if not trusted:
        raise ConflictError("The trusted hotspot context is missing or expired. Reopen the Wi-Fi sign-in page")

    from app.services.mpesa_service import MpesaService
    transaction, voucher = await MpesaService(db).resolve_hotspot_receipt(
        data.receipt,
        phone_number=data.phone_number,
    )
    if str(transaction.router_id or "") != trusted.router_id or str(transaction.site_id or "") != trusted.site_id:
        raise ConflictError("This receipt belongs to a different verified Wi-Fi site")
    if str(voucher.get("router_id") or "") != trusted.router_id or str(voucher.get("site_id") or "") != trusted.site_id:
        raise ConflictError("The paid access record does not match this verified Wi-Fi site")

    normalized_mac = trusted.client_mac.replace("-", ":").upper()
    authorized = {
        str(mac).replace("-", ":").upper()
        for mac in (voucher.get("authorized_macs") or [])
        if mac
    }
    primary = voucher.get("bound_mac") or voucher.get("calling_station_id")
    if primary:
        authorized.add(str(primary).replace("-", ":").upper())
    if normalized_mac not in authorized:
        slots = voucher.get("available_device_slots")
        if slots is None:
            max_devices = max(1, int(voucher.get("max_devices") or 1))
            slots = max(0, max_devices - len(authorized))
        if int(slots) <= 0:
            raise ConflictError("This receipt has reached its allowed device limit")

    await attestation.attest_purchase_device(
        raw_token=hotspot_context,
        device_type="this_device",
        client_ip=trusted.client_ip,
        client_mac=trusted.client_mac,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return success_response(
        message="Paid access verified; submitting the MikroTik login",
        data={
            "verified": True,
            "access_token": transaction.mpesa_receipt_number,
            "login_username": transaction.voucher_code,
            "expires_at": voucher.get("expiry_date").isoformat() if voucher.get("expiry_date") else None,
            "package_name": transaction.account_reference,
        },
    )


@router.post("/free-trial", response_model=dict, status_code=201)
async def request_free_trial(data: HotspotTrialRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Issue a one-time, three-minute voucher bound to a verified captive client."""
    verified_device = await _resolve_hotspot_device(
        HotspotDeviceLookupRequest(
            ip_address=data.ip_address,
            mac_address=data.client_mac,
        ),
        db,
    )
    service = HotspotService(db)
    trial = await service.request_free_trial(verified_device["mac_address"])
    return success_response(
        message="Three-minute trial issued",
        data=trial,
        status_code=201,
    )


@router.get("/plans/{plan_id}", response_model=dict)
async def get_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.get_plan(plan_id)
    return success_response(message="HotSpot plan retrieved", data=_plan_to_response(plan))


@router.patch("/plans/{plan_id}", response_model=dict)
async def update_hotspot_plan(
    request: Request,
    plan_id: str,
    data: HotspotPlanUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.update_plan(plan_id, data)
    return success_response(message="HotSpot plan updated", data=_plan_to_response(plan))


@router.delete("/plans/{plan_id}", response_model=dict)
async def delete_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    await service.delete_plan(plan_id)
    return success_response(message="HotSpot plan deleted")


# ── Live sessions enriched with voucher info ──

@router.get("/routers/{router_id}/active-sessions", response_model=dict)
async def get_hotspot_active_sessions(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Live /ip/hotspot/active sessions from the router (Phase 7), each
    enriched with the voucher record behind it (status, expiry, data cap)."""
    service = HotspotService(db)
    sessions = await service.get_active_sessions_with_vouchers(router_id)
    return success_response(message="Active HotSpot sessions retrieved", data=sessions)
