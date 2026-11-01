from datetime import datetime, timedelta, timezone

from bson import ObjectId
import pytest

from app.routes.routers import _router_diagnostics


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    async def find_one(self, query, projection=None):
        clauses = query.get("$or", [query])
        for document in self.documents:
            if any(document.get(key) == value for clause in clauses for key, value in clause.items()):
                if projection:
                    return {key: value for key, value in document.items() if key == "_id" or projection.get(key)}
                return document
        return None


class FakeDatabase:
    def __init__(self, sites, nas):
        self.sites = FakeCollection(sites)
        self.nas_clients = FakeCollection(nas)


@pytest.mark.asyncio
async def test_router_diagnostics_expose_missing_nas_and_stale_cached_health():
    site_id = ObjectId()
    db = FakeDatabase([{"_id": site_id, "status": "active"}], [])
    router = {
        "_id": ObjectId(), "site_id": str(site_id), "nas_client_id": None,
        "status": "online", "last_checked_at": datetime.now(timezone.utc) - timedelta(hours=2),
    }

    result = await _router_diagnostics(router, db)

    assert result["site_relationship_status"] == "active"
    assert result["nas_relationship_status"] == "not_linked"
    assert result["attestation_configuration_status"] == "eligible"
    assert result["health_freshness"] == "stale"


@pytest.mark.asyncio
async def test_router_diagnostics_mark_dangling_site_ineligible():
    router = {
        "_id": ObjectId(), "site_id": "SITE-001", "nas_client_id": None,
        "status": "offline", "last_checked_at": None,
    }

    result = await _router_diagnostics(router, FakeDatabase([], []))

    assert result["site_relationship_status"] == "missing_site"
    assert result["health_freshness"] == "unknown"
    assert result["attestation_configuration_status"] == "ineligible"
