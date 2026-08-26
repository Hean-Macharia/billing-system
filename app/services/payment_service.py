"""Payment business logic."""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.payment import PaymentInDB, PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentUpdate

logger = get_logger(__name__)


class PaymentService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.payments

    def _generate_transaction_id(self) -> str:
        import random
        now = datetime.now(timezone.utc)
        return f"TXN-{now.year}{now.month:02d}{now.day:02d}-{random.randint(100000, 999999)}"

    async def create(self, data: PaymentCreate, created_by: Optional[str] = None) -> PaymentInDB:
        customer_doc = await self.db.customers.find_one({"_id": ObjectId(data.customer_id)})
        if not customer_doc:
            raise NotFoundError("Customer not found")

        txn_id = data.transaction_id or self._generate_transaction_id()
        existing = await self.collection.find_one({"transaction_id": txn_id})
        if existing:
            raise ConflictError(f"Transaction '{txn_id}' already exists")

        payment_doc = data.model_dump(exclude={"transaction_id"})
        payment_doc["transaction_id"] = txn_id
        payment_doc["customer_code"] = customer_doc.get("customer_code")
        payment_doc["customer_name"] = customer_doc.get("full_name")
        payment_doc["status"] = PaymentStatus.PENDING.value
        payment_doc["currency"] = "KES"
        payment_doc["created_by"] = created_by
        payment_doc["created_at"] = datetime.now(timezone.utc)
        payment_doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(payment_doc)
        payment_doc["_id"] = str(result.inserted_id)
        logger.info(f"Payment recorded: {txn_id} - {data.amount_kes} KES")
        return PaymentInDB(**payment_doc)

    async def get_by_id(self, payment_id: str) -> PaymentInDB:
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(payment_id)})
        except InvalidId:
            raise NotFoundError("Invalid payment ID format")
        if not doc:
            raise NotFoundError("Payment not found")
        doc["_id"] = str(doc["_id"])
        return PaymentInDB(**doc)

    async def get_by_transaction_id(self, txn_id: str) -> PaymentInDB:
        doc = await self.collection.find_one({"transaction_id": txn_id})
        if not doc:
            raise NotFoundError(f"Payment with transaction '{txn_id}' not found")
        doc["_id"] = str(doc["_id"])
        return PaymentInDB(**doc)

    async def list_payments(
        self, customer_id: Optional[str] = None, invoice_id: Optional[str] = None,
        status: Optional[str] = None, payment_method: Optional[str] = None,
        page: int = 1, limit: int = 20,
    ) -> tuple[List[PaymentInDB], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if invoice_id:
            query["invoice_id"] = invoice_id
        if status:
            query["status"] = status
        if payment_method:
            query["payment_method"] = payment_method
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("payment_date", -1)
        payments = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            payments.append(PaymentInDB(**doc))
        return payments, total

    async def update(self, payment_id: str, data: PaymentUpdate) -> PaymentInDB:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one({"_id": ObjectId(payment_id)}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("Payment not found")
        return await self.get_by_id(payment_id)

    async def confirm_payment(self, payment_id: str, invoice_id: Optional[str] = None) -> PaymentInDB:
        now = datetime.now(timezone.utc)
        update = {"$set": {
            "status": PaymentStatus.COMPLETED.value,
            "confirmed_date": now, "updated_at": now,
        }}
        if invoice_id:
            update["$set"]["invoice_id"] = invoice_id

        result = await self.collection.update_one({"_id": ObjectId(payment_id)}, update)
        if result.matched_count == 0:
            raise NotFoundError("Payment not found")

        payment = await self.get_by_id(payment_id)
        if payment.invoice_id and payment.amount_kes > 0:
            from app.services.invoice_service import InvoiceService
            invoice_service = InvoiceService(self.db)
            await invoice_service.apply_payment(payment.invoice_id, payment_id, payment.amount_kes)

        if payment.subscription_id:
            await self.db.subscriptions.update_one(
                {"_id": ObjectId(payment.subscription_id)},
                {"$inc": {"total_paid_kes": payment.amount_kes}, "$set": {"updated_at": now}},
            )
        return payment

    async def process_mpesa_callback(self, checkout_request_id: str, result_code: int,
                                     result_desc: str, receipt_number: Optional[str] = None) -> PaymentInDB:
        doc = await self.collection.find_one({"mpesa_checkout_request_id": checkout_request_id})
        if not doc:
            raise NotFoundError("Payment not found for this checkout request")

        payment_id = str(doc["_id"])
        status = PaymentStatus.COMPLETED.value if result_code == 0 else PaymentStatus.FAILED.value
        update = {"$set": {
            "status": status, "mpesa_result_code": result_code,
            "mpesa_result_desc": result_desc, "mpesa_callback_received": True,
            "updated_at": datetime.now(timezone.utc),
        }}
        if receipt_number:
            update["$set"]["mpesa_receipt_number"] = receipt_number

        await self.collection.update_one({"_id": ObjectId(payment_id)}, update)
        if result_code == 0:
            return await self.confirm_payment(payment_id)
        return await self.get_by_id(payment_id)