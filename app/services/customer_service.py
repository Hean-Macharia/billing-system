"""Customer business logic."""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.customer import Customer, CustomerInDB, CustomerStatus
from app.schemas.customer import CustomerCreate, CustomerUpdate

logger = get_logger(__name__)


class CustomerService:
    """Service layer for customer operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.customers

    async def create(self, data: CustomerCreate, created_by: Optional[str] = None) -> CustomerInDB:
        """Create a new customer."""
        # Check unique customer_code
        existing = await self.collection.find_one({"customer_code": data.customer_code})
        if existing:
            raise ConflictError(f"Customer with code '{data.customer_code}' already exists")

        # Check unique email if provided
        if data.email:
            existing = await self.collection.find_one({"email": data.email})
            if existing:
                raise ConflictError(f"Customer with email '{data.email}' already exists")

        customer_doc = data.model_dump(exclude_unset=True)
        customer_doc["status"] = CustomerStatus.PENDING.value
        customer_doc["outstanding_balance"] = 0.0
        customer_doc["credit_limit"] = 0.0
        customer_doc["created_by"] = created_by
        customer_doc["created_at"] = datetime.now(timezone.utc)
        customer_doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(customer_doc)
        customer_doc["_id"] = str(result.inserted_id)
        logger.info(f"Customer created: {data.customer_code} - {data.full_name}")
        return CustomerInDB(**customer_doc)

    async def get_by_id(self, customer_id: str) -> CustomerInDB:
        """Get customer by ID."""
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(customer_id)})
        except InvalidId:
            raise NotFoundError("Invalid customer ID format")
        if not doc:
            raise NotFoundError("Customer not found")
        doc["_id"] = str(doc["_id"])
        return CustomerInDB(**doc)

    async def get_by_code(self, customer_code: str) -> CustomerInDB:
        """Get customer by customer code."""
        doc = await self.collection.find_one({"customer_code": customer_code})
        if not doc:
            raise NotFoundError(f"Customer with code '{customer_code}' not found")
        doc["_id"] = str(doc["_id"])
        return CustomerInDB(**doc)

    async def list_customers(
        self,
        status: Optional[str] = None,
        customer_type: Optional[str] = None,
        search: Optional[str] = None,
        assigned_to: Optional[str] = None,
        package_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[List[CustomerInDB], int]:
        """List customers with filters."""
        query = {}
        if status:
            query["status"] = status
        if customer_type:
            query["customer_type"] = customer_type
        if assigned_to:
            query["assigned_to"] = assigned_to
        if package_id:
            query["current_package.package_id"] = package_id
        if search:
            query["$or"] = [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"customer_code": {"$regex": search, "$options": "i"}},
                {"company_name": {"$regex": search, "$options": "i"}},
            ]

        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)

        customers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            customers.append(CustomerInDB(**doc))

        return customers, total

    async def update(self, customer_id: str, data: CustomerUpdate) -> CustomerInDB:
        """Update customer fields."""
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")

        # Check email uniqueness if changing email
        if "email" in update_data and update_data["email"]:
            existing = await self.collection.find_one({
                "email": update_data["email"],
                "_id": {"$ne": ObjectId(customer_id)},
            })
            if existing:
                raise ConflictError(f"Email '{update_data['email']}' already in use")

        update_data["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": update_data},
        )
        if result.matched_count == 0:
            raise NotFoundError("Customer not found")

        logger.info(f"Customer updated: {customer_id}")
        return await self.get_by_id(customer_id)

    async def delete(self, customer_id: str) -> None:
        """Soft delete a customer (set status to inactive)."""
        result = await self.collection.update_one(
            {"_id": ObjectId(customer_id)},
            {
                "$set": {
                    "status": CustomerStatus.INACTIVE.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if result.matched_count == 0:
            raise NotFoundError("Customer not found")
        logger.info(f"Customer deactivated: {customer_id}")

    async def hard_delete(self, customer_id: str) -> None:
        """Permanently delete a customer. Admin only."""
        result = await self.collection.delete_one({"_id": ObjectId(customer_id)})
        if result.deleted_count == 0:
            raise NotFoundError("Customer not found")
        logger.info(f"Customer permanently deleted: {customer_id}")

    async def update_status(self, customer_id: str, status: str) -> CustomerInDB:
        """Update customer status."""
        valid_statuses = ["active", "inactive", "suspended", "pending"]
        if status not in valid_statuses:
            raise ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")

        result = await self.collection.update_one(
            {"_id": ObjectId(customer_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if result.matched_count == 0:
            raise NotFoundError("Customer not found")

        logger.info(f"Customer {customer_id} status changed to {status}")
        return await self.get_by_id(customer_id)

    async def assign_package(self, customer_id: str, package_data: dict) -> CustomerInDB:
        """Assign a service package to a customer."""
        customer = await self.get_by_id(customer_id)

        # Move current package to history if exists
        if customer.current_package:
            await self.collection.update_one(
                {"_id": ObjectId(customer_id)},
                {"$push": {"package_history": customer.current_package.model_dump()}},
            )

        package_data["status"] = "active"
        package_data["activation_date"] = datetime.now(timezone.utc)

        result = await self.collection.update_one(
            {"_id": ObjectId(customer_id)},
            {
                "$set": {
                    "current_package": package_data,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if result.matched_count == 0:
            raise NotFoundError("Customer not found")

        logger.info(f"Package assigned to customer {customer_id}")
        return await self.get_by_id(customer_id)

    async def update_balance(self, customer_id: str, amount: float) -> CustomerInDB:
        """Update customer outstanding balance."""
        result = await self.collection.update_one(
            {"_id": ObjectId(customer_id)},
            {
                "$inc": {"outstanding_balance": amount},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        if result.matched_count == 0:
            raise NotFoundError("Customer not found")
        return await self.get_by_id(customer_id)