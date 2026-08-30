"""RADIUS admin service for NAS and user management."""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.radius import NasClient, NasType, RadiusUser, RadiusUserType
from app.schemas.radius import NasClientCreate, NasClientUpdate, RadiusUserCreate, RadiusUserUpdate

logger = get_logger(__name__)


class RadiusAdminService:
    """Administrative operations for RADIUS infrastructure."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.nas_collection = db.nas_clients
        self.user_collection = db.radius_users

    # ── NAS Clients ──

    async def create_nas(self, data: NasClientCreate) -> NasClient:
        existing = await self.nas_collection.find_one({"ip_address": data.ip_address})
        if existing:
            raise ConflictError(f"NAS with IP {data.ip_address} already exists")

        doc = data.model_dump()
        doc["status"] = "active"
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.nas_collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info(f"NAS client created: {data.name} @ {data.ip_address}")
        return NasClient(**doc)

    async def get_nas(self, nas_id: str) -> NasClient:
        doc = await self.nas_collection.find_one({"_id": ObjectId(nas_id)})
        if not doc:
            raise NotFoundError("NAS client not found")
        doc["_id"] = str(doc["_id"])
        return NasClient(**doc)

    async def get_nas_by_ip(self, ip_address: str) -> Optional[NasClient]:
        doc = await self.nas_collection.find_one({"ip_address": ip_address})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return NasClient(**doc)

    async def list_nas(
        self, site_id: Optional[str] = None, status: Optional[str] = None, page: int = 1, limit: int = 20
    ) -> tuple[List[NasClient], int]:
        query = {}
        if site_id:
            query["site_id"] = site_id
        if status:
            query["status"] = status

        skip = (page - 1) * limit
        total = await self.nas_collection.count_documents(query)
        cursor = self.nas_collection.find(query).skip(skip).limit(limit)
        clients = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            clients.append(NasClient(**doc))
        return clients, total

    async def update_nas(self, nas_id: str, data: NasClientUpdate) -> NasClient:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)

        result = await self.nas_collection.update_one(
            {"_id": ObjectId(nas_id)}, {"$set": update_data}
        )
        if result.matched_count == 0:
            raise NotFoundError("NAS client not found")
        return await self.get_nas(nas_id)

    async def delete_nas(self, nas_id: str) -> None:
        result = await self.nas_collection.delete_one({"_id": ObjectId(nas_id)})
        if result.deleted_count == 0:
            raise NotFoundError("NAS client not found")

    # ── RADIUS Users ──

    async def create_user(self, data: RadiusUserCreate) -> RadiusUser:
        existing = await self.user_collection.find_one({"username": data.username})
        if existing:
            raise ConflictError(f"RADIUS user '{data.username}' already exists")

        doc = data.model_dump()
        doc["status"] = "active"
        doc["total_sessions"] = 0
        doc["total_online_time_sec"] = 0
        doc["total_input_bytes"] = 0
        doc["total_output_bytes"] = 0
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.user_collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info(f"RADIUS user created: {data.username} ({data.user_type.value})")
        return RadiusUser(**doc)

    async def get_user(self, user_id: str) -> RadiusUser:
        doc = await self.user_collection.find_one({"_id": ObjectId(user_id)})
        if not doc:
            raise NotFoundError("RADIUS user not found")
        doc["_id"] = str(doc["_id"])
        return RadiusUser(**doc)

    async def get_user_by_username(self, username: str) -> Optional[RadiusUser]:
        doc = await self.user_collection.find_one({"username": username})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return RadiusUser(**doc)

    async def list_users(
        self,
        customer_id: Optional[str] = None,
        site_id: Optional[str] = None,
        user_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[List[RadiusUser], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if site_id:
            query["site_id"] = site_id
        if user_type:
            query["user_type"] = user_type
        if status:
            query["status"] = status

        skip = (page - 1) * limit
        total = await self.user_collection.count_documents(query)
        cursor = self.user_collection.find(query).skip(skip).limit(limit)
        users = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            users.append(RadiusUser(**doc))
        return users, total

    async def update_user(self, user_id: str, data: RadiusUserUpdate) -> RadiusUser:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)

        result = await self.user_collection.update_one(
            {"_id": ObjectId(user_id)}, {"$set": update_data}
        )
        if result.matched_count == 0:
            raise NotFoundError("RADIUS user not found")
        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> None:
        result = await self.user_collection.delete_one({"_id": ObjectId(user_id)})
        if result.deleted_count == 0:
            raise NotFoundError("RADIUS user not found")

    async def sync_user_from_subscription(self, subscription_id: str) -> RadiusUser:
        """Auto-create/update RADIUS user from an active subscription."""
        sub = await self.db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
        if not sub:
            raise NotFoundError("Subscription not found")

        customer_id = str(sub["customer_id"]) if isinstance(sub["customer_id"], ObjectId) else sub["customer_id"]
        package_id = str(sub["package_id"]) if isinstance(sub["package_id"], ObjectId) else sub.get("package_id")
        site_id = str(sub["site_id"]) if isinstance(sub.get("site_id"), ObjectId) else sub.get("site_id")

        # Get package details for rate limits
        package = None
        if package_id:
            pkg = await self.db.service_plans.find_one({"_id": ObjectId(package_id)})
            if pkg:
                package = pkg

        # Get customer for username generation
        customer = await self.db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            raise NotFoundError("Customer not found")

        username = sub.get("pppoe_username") or customer.get("customer_code", "").lower()
        if not username:
            raise ValidationError("Cannot generate username: missing customer_code or pppoe_username")

        # Check if user already exists
        existing = await self.get_user_by_username(username)
        if existing:
            # Update existing
            update = {
                "subscription_id": subscription_id,
                "package_id": package_id,
                "site_id": site_id,
                "status": "active" if sub.get("status") == "active" else sub.get("status"),
                "updated_at": datetime.now(timezone.utc),
            }
            if package:
                update["rate_limit"] = package.get("rate_limit")
                update["session_timeout"] = package.get("session_timeout")
                update["framed_ip_pool"] = package.get("framed_ip_pool")
                update["data_cap_bytes"] = package.get("data_cap_bytes")
            await self.user_collection.update_one(
                {"_id": ObjectId(existing.id)}, {"$set": update}
            )
            return await self.get_user(existing.id)

        # Create new
        password = sub.get("pppoe_password") or customer.get("phone", "changeme")
        create_data = RadiusUserCreate(
            username=username,
            password=password,
            user_type=RadiusUserType.PPPOE,
            customer_id=customer_id,
            service_id=str(sub.get("service_id")) if sub.get("service_id") else None,
            subscription_id=subscription_id,
            site_id=site_id,
            package_id=package_id,
            rate_limit=package.get("rate_limit") if package else None,
            session_timeout=package.get("session_timeout") if package else None,
            framed_ip_pool=package.get("framed_ip_pool") if package else None,
            data_cap_bytes=package.get("data_cap_bytes") if package else None,
        )
        return await self.create_user(create_data)