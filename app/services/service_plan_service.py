"""Service plan business logic."""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.service import ServicePlanInDB, ServiceStatus
from app.schemas.service import ServicePlanCreate, ServicePlanUpdate

logger = get_logger(__name__)


class ServicePlanService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.service_plans

    async def create(self, data: ServicePlanCreate, created_by: Optional[str] = None) -> ServicePlanInDB:
        existing = await self.collection.find_one({"plan_code": data.plan_code})
        if existing:
            raise ConflictError(f"Plan with code '{data.plan_code}' already exists")

        plan_doc = data.model_dump()
        plan_doc["status"] = ServiceStatus.ACTIVE.value
        plan_doc["created_by"] = created_by
        plan_doc["created_at"] = datetime.now(timezone.utc)
        plan_doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(plan_doc)
        plan_doc["_id"] = str(result.inserted_id)
        logger.info(f"Service plan created: {data.plan_code} - {data.name}")
        return ServicePlanInDB(**plan_doc)

    async def get_by_id(self, plan_id: str) -> ServicePlanInDB:
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(plan_id)})
        except InvalidId:
            raise NotFoundError("Invalid plan ID format")
        if not doc:
            raise NotFoundError("Service plan not found")
        doc["_id"] = str(doc["_id"])
        return ServicePlanInDB(**doc)

    async def get_by_code(self, plan_code: str) -> ServicePlanInDB:
        doc = await self.collection.find_one({"plan_code": plan_code})
        if not doc:
            raise NotFoundError(f"Plan with code '{plan_code}' not found")
        doc["_id"] = str(doc["_id"])
        return ServicePlanInDB(**doc)

    async def list_plans(
        self, status: Optional[str] = None, service_type: Optional[str] = None,
        search: Optional[str] = None, page: int = 1, limit: int = 20,
    ) -> tuple[List[ServicePlanInDB], int]:
        query = {}
        if status:
            query["status"] = status
        if service_type:
            query["service_type"] = service_type
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"plan_code": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("popularity_score", -1)
        plans = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            plans.append(ServicePlanInDB(**doc))
        return plans, total

    async def update(self, plan_id: str, data: ServicePlanUpdate) -> ServicePlanInDB:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one({"_id": ObjectId(plan_id)}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("Service plan not found")
        return await self.get_by_id(plan_id)

    async def delete(self, plan_id: str) -> None:
        result = await self.collection.update_one(
            {"_id": ObjectId(plan_id)},
            {"$set": {"status": ServiceStatus.DEPRECATED.value, "updated_at": datetime.now(timezone.utc)}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Service plan not found")
        logger.info(f"Service plan deprecated: {plan_id}")