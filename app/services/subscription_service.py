"""Subscription business logic."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.subscription import SubscriptionInDB, SubscriptionStatus
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate

logger = get_logger(__name__)


class SubscriptionService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.subscriptions

    def _calculate_next_billing(self, start_date: datetime, billing_cycle: str) -> datetime:
        cycle_map = {
            "daily": timedelta(days=1), "weekly": timedelta(weeks=1),
            "monthly": timedelta(days=30), "quarterly": timedelta(days=90),
            "semi_annual": timedelta(days=180), "yearly": timedelta(days=365),
        }
        return start_date + cycle_map.get(billing_cycle, timedelta(days=30))

    async def create(self, data: SubscriptionCreate, created_by: Optional[str] = None) -> SubscriptionInDB:
        customer_doc = await self.db.customers.find_one({"_id": ObjectId(data.customer_id)})
        if not customer_doc:
            raise NotFoundError("Customer not found")
        plan_doc = await self.db.service_plans.find_one({"_id": ObjectId(data.plan_id)})
        if not plan_doc:
            raise NotFoundError("Service plan not found")

        existing = await self.collection.find_one({
            "customer_id": data.customer_id, "plan_id": data.plan_id,
            "status": {"$in": ["active", "pending", "trial"]},
        })
        if existing:
            raise ConflictError("Customer already has an active subscription to this plan")

        next_billing = self._calculate_next_billing(data.start_date, plan_doc.get("billing_cycle", "monthly"))

        sub_doc = data.model_dump()
        sub_doc["customer_code"] = customer_doc.get("customer_code")
        sub_doc["customer_name"] = customer_doc.get("full_name")
        sub_doc["plan_code"] = plan_doc.get("plan_code")
        sub_doc["plan_name"] = plan_doc.get("name")
        sub_doc["status"] = SubscriptionStatus.PENDING.value
        sub_doc["next_billing_date"] = next_billing
        sub_doc["data_cap_gb"] = plan_doc.get("data_cap_gb")
        sub_doc["created_by"] = created_by
        sub_doc["created_at"] = datetime.now(timezone.utc)
        sub_doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(sub_doc)
        sub_doc["_id"] = str(result.inserted_id)
        logger.info(f"Subscription created: {sub_doc['plan_name']} for {sub_doc['customer_code']}")
        return SubscriptionInDB(**sub_doc)

    async def get_by_id(self, sub_id: str) -> SubscriptionInDB:
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(sub_id)})
        except InvalidId:
            raise NotFoundError("Invalid subscription ID format")
        if not doc:
            raise NotFoundError("Subscription not found")
        doc["_id"] = str(doc["_id"])
        return SubscriptionInDB(**doc)

    async def list_subscriptions(
        self, customer_id: Optional[str] = None, plan_id: Optional[str] = None,
        status: Optional[str] = None, page: int = 1, limit: int = 20,
    ) -> tuple[List[SubscriptionInDB], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if plan_id:
            query["plan_id"] = plan_id
        if status:
            query["status"] = status
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        subs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            subs.append(SubscriptionInDB(**doc))
        return subs, total

    async def update(self, sub_id: str, data: SubscriptionUpdate) -> SubscriptionInDB:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one({"_id": ObjectId(sub_id)}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("Subscription not found")
        return await self.get_by_id(sub_id)

    async def cancel(self, sub_id: str, reason: Optional[str] = None) -> SubscriptionInDB:
        result = await self.collection.update_one(
            {"_id": ObjectId(sub_id)},
            {"$set": {
                "status": SubscriptionStatus.CANCELLED.value,
                "cancelled_at": datetime.now(timezone.utc),
                "cancellation_reason": reason,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        if result.matched_count == 0:
            raise NotFoundError("Subscription not found")
        return await self.get_by_id(sub_id)

    async def mark_installed(self, sub_id: str, technician_id: Optional[str] = None) -> SubscriptionInDB:
        result = await self.collection.update_one(
            {"_id": ObjectId(sub_id)},
            {"$set": {
                "installation_completed": True,
                "installation_date": datetime.now(timezone.utc),
                "assigned_technician_id": technician_id,
                "status": SubscriptionStatus.ACTIVE.value,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        if result.matched_count == 0:
            raise NotFoundError("Subscription not found")
        return await self.get_by_id(sub_id)

    async def get_billable_subscriptions(self, billing_date: Optional[datetime] = None) -> List[SubscriptionInDB]:
        if billing_date is None:
            billing_date = datetime.now(timezone.utc)
        query = {"status": {"$in": ["active", "trial"]}, "next_billing_date": {"$lte": billing_date}}
        cursor = self.collection.find(query)
        subs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            subs.append(SubscriptionInDB(**doc))
        return subs