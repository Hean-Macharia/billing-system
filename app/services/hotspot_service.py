"""HotSpot plan (profile) service - simple CRUD, plus a helper that
cross-references Phase 7's live router sessions with voucher records so
you can see, per active HotSpot user, which voucher they're on.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.hotspot import HotspotPlan
from app.schemas.hotspot import HotspotPlanCreate, HotspotPlanUpdate
from app.services.router_service import RouterService

logger = get_logger(__name__)


class HotspotService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.plans = db.hotspot_plans
        self.vouchers = db.vouchers

    def _oid(self, id_str: str, label: str = "Resource") -> ObjectId:
        try:
            return ObjectId(id_str)
        except Exception as exc:
            raise NotFoundError(f"{label} not found") from exc

    # ------------------------------------------------------------------ #
    # Plan CRUD
    # ------------------------------------------------------------------ #
    async def create_plan(self, data: HotspotPlanCreate) -> HotspotPlan:
        existing = await self.plans.find_one({"name": data.name, "site_id": data.site_id})
        if existing:
            raise ConflictError(f"A plan named '{data.name}' already exists for this site")

        now = datetime.now(timezone.utc)
        doc = data.model_dump()
        doc["created_at"] = now
        doc["updated_at"] = now
        result = await self.plans.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return HotspotPlan(**doc)

    async def get_plan(self, plan_id: str) -> HotspotPlan:
        doc = await self.plans.find_one({"_id": self._oid(plan_id, "Plan")})
        if not doc:
            raise NotFoundError("HotSpot plan not found")
        doc["_id"] = str(doc["_id"])
        return HotspotPlan(**doc)

    async def list_plans(self, site_id: Optional[str] = None, active_only: bool = False):
        query = {}
        if site_id:
            query["site_id"] = site_id
        if active_only:
            query["is_active"] = True
        cursor = self.plans.find(query).sort("sort_order", 1)
        plans = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            plans.append(HotspotPlan(**doc))
        return plans

    async def update_plan(self, plan_id: str, data: HotspotPlanUpdate) -> HotspotPlan:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            return await self.get_plan(plan_id)
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.plans.update_one({"_id": self._oid(plan_id, "Plan")}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("HotSpot plan not found")
        return await self.get_plan(plan_id)

    async def delete_plan(self, plan_id: str) -> None:
        result = await self.plans.delete_one({"_id": self._oid(plan_id, "Plan")})
        if result.deleted_count == 0:
            raise NotFoundError("HotSpot plan not found")

    # ------------------------------------------------------------------ #
    # Live HotSpot sessions enriched with voucher info
    # ------------------------------------------------------------------ #
    async def get_active_sessions_with_vouchers(self, router_id: str) -> list:
        """Cross-references Phase 7's live /ip/hotspot/active list with the
        vouchers collection (the HotSpot 'user' field IS the voucher_code
        for voucher-authenticated sessions) so an operator can see exactly
        which voucher is behind each connected device.
        """
        router_service = RouterService(self.db)
        active = await router_service.get_active_users(router_id)
        hotspot_sessions = active.get("hotspot", [])

        codes = [s.get("user") for s in hotspot_sessions if s.get("user")]
        vouchers_by_code = {}
        if codes:
            cursor = self.vouchers.find({"voucher_code": {"$in": codes}})
            async for doc in cursor:
                vouchers_by_code[doc["voucher_code"]] = {
                    "voucher_id": str(doc["_id"]),
                    "status": doc.get("status"),
                    "expiry_date": doc.get("expiry_date"),
                    "data_allowance_mb": doc.get("data_allowance_mb"),
                }

        enriched = []
        for session in hotspot_sessions:
            code = session.get("user")
            enriched.append({**session, "voucher": vouchers_by_code.get(code)})
        return enriched
