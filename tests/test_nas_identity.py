from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.services.nas_identity_service import resolve_nas_identity


@pytest.fixture
def radius_db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["nas_identity_test"]
    client.close()


async def add_site(db, name, status="active"):
    site_id = ObjectId()
    await db.sites.insert_one({"_id": site_id, "name": name, "status": status})
    return site_id


async def add_router_nas(db, site_id, *, nas_ip, nas_identifier, router_status="online", nas_status="active"):
    nas_id = ObjectId()
    router_id = ObjectId()
    await db.nas_clients.insert_one({
        "_id": nas_id,
        "name": f"NAS {nas_identifier}",
        "ip_address": nas_ip,
        "nas_identifier": nas_identifier,
        "site_id": str(site_id) if site_id else None,
        "status": nas_status,
    })
    await db.routers.insert_one({
        "_id": router_id,
        "name": f"Router {nas_identifier}",
        "ip_address": f"10.10.0.{1 if nas_identifier == 'NYA-EDGE-1' else 2}",
        "nas_client_id": str(nas_id),
        "site_id": str(site_id) if site_id else None,
        "status": router_status,
        "hotspot_subnet": "192.168.89.0/24",
    })
    return nas_id, router_id


@pytest.mark.asyncio
async def test_known_nas_ip_and_identifier_resolve_same_router_and_site(radius_db):
    nyahururu = await add_site(radius_db, "Nyaururu")
    await add_site(radius_db, "Nakuru")
    nas_id, router_id = await add_router_nas(
        radius_db,
        nyahururu,
        nas_ip="10.0.0.11",
        nas_identifier="NYA-EDGE-1",
    )

    by_ip = await resolve_nas_identity(radius_db, "10.0.0.11", None)
    by_identifier = await resolve_nas_identity(radius_db, None, "NYA-EDGE-1")
    by_both = await resolve_nas_identity(radius_db, "10.0.0.11", "NYA-EDGE-1")

    for identity in (by_ip, by_identifier, by_both):
        assert identity.resolved
        assert identity.nas_client_id == str(nas_id)
        assert identity.router_id == str(router_id)
        assert identity.site_id == str(nyahururu)


@pytest.mark.asyncio
async def test_overlapping_hotspot_subnets_do_not_confuse_sites(radius_db):
    nyahururu = await add_site(radius_db, "Nyaururu")
    nakuru = await add_site(radius_db, "Nakuru")
    _, nyahururu_router = await add_router_nas(
        radius_db, nyahururu, nas_ip="10.0.0.11", nas_identifier="NYA-EDGE-1"
    )
    _, nakuru_router = await add_router_nas(
        radius_db, nakuru, nas_ip="10.0.0.12", nas_identifier="NAK-EDGE-1"
    )

    assert (await resolve_nas_identity(radius_db, "10.0.0.11", None)).router_id == str(nyahururu_router)
    assert (await resolve_nas_identity(radius_db, "10.0.0.12", None)).router_id == str(nakuru_router)


@pytest.mark.asyncio
async def test_nas_ip_and_identifier_pointing_to_different_routers_are_ambiguous(radius_db):
    site = await add_site(radius_db, "Nakuru")
    await add_router_nas(radius_db, site, nas_ip="10.0.0.11", nas_identifier="NYA-EDGE-1")
    await add_router_nas(radius_db, site, nas_ip="10.0.0.12", nas_identifier="NAK-EDGE-1")

    identity = await resolve_nas_identity(radius_db, "10.0.0.11", "NAK-EDGE-1")

    assert identity.status == "ambiguous"
    assert identity.reason == "nas_attributes_disagree"


@pytest.mark.asyncio
async def test_unknown_nas_and_duplicate_identifier_fail_closed(radius_db):
    site = await add_site(radius_db, "Nakuru")
    await add_router_nas(radius_db, site, nas_ip="10.0.0.11", nas_identifier="DUPLICATE")
    second_nas_id = ObjectId()
    await radius_db.nas_clients.insert_one({
        "_id": second_nas_id,
        "name": "Duplicate NAS identity",
        "ip_address": "10.0.0.12",
        "nas_identifier": "DUPLICATE",
        "site_id": str(site),
        "status": "active",
    })

    unknown = await resolve_nas_identity(radius_db, "10.0.0.99", None)
    duplicate = await resolve_nas_identity(radius_db, None, "DUPLICATE")

    assert unknown.status == "unresolved"
    assert unknown.reason == "unknown_nas_ip"
    assert duplicate.status == "ambiguous"
    assert duplicate.reason == "duplicate_nas_mapping"


@pytest.mark.asyncio
async def test_disabled_nas_router_and_site_are_not_resolved(radius_db):
    site = await add_site(radius_db, "Nakuru")
    await add_router_nas(
        radius_db,
        site,
        nas_ip="10.0.0.11",
        nas_identifier="DISABLED-NAS",
        nas_status="disabled",
    )
    await add_router_nas(
        radius_db,
        site,
        nas_ip="10.0.0.12",
        nas_identifier="DISABLED-ROUTER",
        router_status="disabled",
    )
    inactive_site = await add_site(radius_db, "Planned", status="inactive")
    await add_router_nas(
        radius_db,
        inactive_site,
        nas_ip="10.0.0.13",
        nas_identifier="INACTIVE-SITE",
    )

    assert (await resolve_nas_identity(radius_db, "10.0.0.11", None)).reason == "nas_disabled"
    assert (await resolve_nas_identity(radius_db, "10.0.0.12", None)).reason == "router_disabled"
    assert (await resolve_nas_identity(radius_db, "10.0.0.13", None)).reason == "site_not_active"


@pytest.mark.asyncio
async def test_missing_unknown_and_conflicting_site_mapping_fail_closed(radius_db):
    missing_site_nas = ObjectId()
    missing_site_router = ObjectId()
    await radius_db.nas_clients.insert_one({
        "_id": missing_site_nas,
        "ip_address": "10.0.0.11",
        "nas_identifier": "NO-SITE",
        "status": "active",
    })
    await radius_db.routers.insert_one({
        "_id": missing_site_router,
        "ip_address": "10.10.0.11",
        "nas_client_id": str(missing_site_nas),
        "status": "online",
    })
    unknown_site = ObjectId()
    await radius_db.nas_clients.insert_one({
        "_id": ObjectId(), "ip_address": "10.0.0.12", "site_id": str(unknown_site),
        "nas_identifier": "UNKNOWN-SITE", "status": "active",
    })
    await radius_db.routers.insert_one({
        "_id": ObjectId(), "ip_address": "10.10.0.12", "nas_client_id": str(
            (await radius_db.nas_clients.find_one({"nas_identifier": "UNKNOWN-SITE"}))[
                "_id"
            ]
        ), "site_id": str(unknown_site), "status": "online",
    })
    site_a = await add_site(radius_db, "Site A")
    site_b = await add_site(radius_db, "Site B")
    mismatch_nas = ObjectId()
    await radius_db.nas_clients.insert_one({
        "_id": mismatch_nas, "ip_address": "10.0.0.13", "site_id": str(site_a),
        "nas_identifier": "SITE-MISMATCH", "status": "active",
    })
    await radius_db.routers.insert_one({
        "_id": ObjectId(), "ip_address": "10.10.0.13", "nas_client_id": str(mismatch_nas),
        "site_id": str(site_b), "status": "online",
    })

    assert (await resolve_nas_identity(radius_db, "10.0.0.11", None)).reason == "missing_site_mapping"
    assert (await resolve_nas_identity(radius_db, "10.0.0.12", None)).reason == "unknown_site"
    assert (await resolve_nas_identity(radius_db, "10.0.0.13", None)).reason == "router_nas_site_disagree"


@pytest.mark.asyncio
async def test_legacy_router_can_be_resolved_only_by_exact_unique_nas_ip(radius_db):
    site = await add_site(radius_db, "Nakuru")
    await radius_db.nas_clients.insert_one({
        "_id": ObjectId(), "ip_address": "10.0.0.11", "site_id": str(site),
        "nas_identifier": "LEGACY-NAS", "status": "active",
    })
    legacy_router = ObjectId()
    await radius_db.routers.insert_one({
        "_id": legacy_router, "ip_address": "10.0.0.11", "site_id": str(site), "status": "unknown",
    })

    identity = await resolve_nas_identity(radius_db, "10.0.0.11", "LEGACY-NAS")

    assert identity.resolved
    assert identity.router_id == str(legacy_router)
    assert identity.site_id == str(site)

