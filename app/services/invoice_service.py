"""Invoice business logic."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.invoice import InvoiceInDB, InvoiceLineItem, InvoiceStatus
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate

logger = get_logger(__name__)


class InvoiceService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.invoices

    def _generate_invoice_number(self) -> str:
        import random
        now = datetime.now(timezone.utc)
        prefix = f"INV-{now.year}-{now.month:02d}"
        suffix = random.randint(1000, 9999)
        return f"{prefix}-{suffix}"

    async def create(self, data: InvoiceCreate, created_by: Optional[str] = None) -> InvoiceInDB:
        customer_doc = await self.db.customers.find_one({"_id": ObjectId(data.customer_id)})
        if not customer_doc:
            raise NotFoundError("Customer not found")

        invoice_number = self._generate_invoice_number()
        subtotal = sum(item.total_kes for item in data.line_items)
        tax_amount = subtotal * (data.tax_rate_percent / 100)
        total = subtotal + tax_amount - data.discount_kes

        invoice_doc = data.model_dump()
        invoice_doc["invoice_number"] = invoice_number
        invoice_doc["customer_code"] = customer_doc.get("customer_code")
        invoice_doc["customer_name"] = customer_doc.get("full_name")
        invoice_doc["customer_email"] = customer_doc.get("email")
        invoice_doc["status"] = InvoiceStatus.DRAFT.value
        invoice_doc["subtotal_kes"] = subtotal
        invoice_doc["tax_amount_kes"] = tax_amount
        invoice_doc["total_kes"] = total
        invoice_doc["balance_due_kes"] = total
        invoice_doc["amount_paid_kes"] = 0.0
        invoice_doc["payment_ids"] = []
        invoice_doc["created_by"] = created_by
        invoice_doc["created_at"] = datetime.now(timezone.utc)
        invoice_doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(invoice_doc)
        invoice_doc["_id"] = str(result.inserted_id)
        logger.info(f"Invoice created: {invoice_number} for {invoice_doc['customer_code']}")
        return InvoiceInDB(**invoice_doc)

    async def generate_from_subscription(self, subscription_id: str, created_by: Optional[str] = None) -> InvoiceInDB:
        sub_doc = await self.db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
        if not sub_doc:
            raise NotFoundError("Subscription not found")

        customer_id = sub_doc["customer_id"]
        monthly_price = sub_doc.get("monthly_price_kes", 0)
        setup_fee = sub_doc.get("setup_fee_kes", 0)
        equipment_fee = sub_doc.get("equipment_fee_kes", 0)
        discount = sub_doc.get("discount_kes", 0)

        line_items = []
        if monthly_price > 0:
            line_items.append(InvoiceLineItem(
                description=f"Monthly service: {sub_doc.get('plan_name', 'Internet Service')}",
                quantity=1, unit_price_kes=monthly_price, total_kes=monthly_price,
                item_type="service", subscription_id=subscription_id,
            ))
        if setup_fee > 0:
            line_items.append(InvoiceLineItem(
                description="Setup/Installation Fee", quantity=1,
                unit_price_kes=setup_fee, total_kes=setup_fee, item_type="setup",
            ))
        if equipment_fee > 0:
            line_items.append(InvoiceLineItem(
                description="Equipment Fee", quantity=1,
                unit_price_kes=equipment_fee, total_kes=equipment_fee, item_type="equipment",
            ))

        now = datetime.now(timezone.utc)
        due_date = now + timedelta(days=7)

        invoice_data = InvoiceCreate(
            customer_id=customer_id, subscription_id=subscription_id,
            invoice_date=now, due_date=due_date, line_items=line_items, discount_kes=discount,
        )
        invoice = await self.create(invoice_data, created_by)

        await self.db.subscriptions.update_one(
            {"_id": ObjectId(subscription_id)},
            {"$set": {
                "last_billed_date": now, "next_billing_date": now + timedelta(days=30),
                "updated_at": now,
            }, "$push": {"invoice_ids": str(invoice.id)}, "$inc": {"total_billed_kes": invoice.total_kes}},
        )
        await self.db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"last_billed_at": now, "updated_at": now}},
        )
        return invoice

    async def get_by_id(self, invoice_id: str) -> InvoiceInDB:
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(invoice_id)})
        except InvalidId:
            raise NotFoundError("Invalid invoice ID format")
        if not doc:
            raise NotFoundError("Invoice not found")
        doc["_id"] = str(doc["_id"])
        return InvoiceInDB(**doc)

    async def get_by_number(self, invoice_number: str) -> InvoiceInDB:
        doc = await self.collection.find_one({"invoice_number": invoice_number})
        if not doc:
            raise NotFoundError(f"Invoice '{invoice_number}' not found")
        doc["_id"] = str(doc["_id"])
        return InvoiceInDB(**doc)

    async def list_invoices(
        self, customer_id: Optional[str] = None, status: Optional[str] = None,
        overdue_only: bool = False, page: int = 1, limit: int = 20,
    ) -> tuple[List[InvoiceInDB], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if status:
            query["status"] = status
        if overdue_only:
            query["status"] = {"$in": ["sent", "partial", "viewed"]}
            query["due_date"] = {"$lt": datetime.now(timezone.utc)}
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        invoices = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            invoices.append(InvoiceInDB(**doc))
        return invoices, total

    async def update(self, invoice_id: str, data: InvoiceUpdate) -> InvoiceInDB:
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one({"_id": ObjectId(invoice_id)}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("Invoice not found")
        return await self.get_by_id(invoice_id)

    async def mark_sent(self, invoice_id: str, sent_by: Optional[str] = None) -> InvoiceInDB:
        result = await self.collection.update_one(
            {"_id": ObjectId(invoice_id)},
            {"$set": {
                "status": InvoiceStatus.SENT.value, "sent_date": datetime.now(timezone.utc),
                "sent_by": sent_by, "updated_at": datetime.now(timezone.utc),
            }},
        )
        if result.matched_count == 0:
            raise NotFoundError("Invoice not found")
        return await self.get_by_id(invoice_id)

    async def apply_payment(self, invoice_id: str, payment_id: str, amount: float) -> InvoiceInDB:
        invoice = await self.get_by_id(invoice_id)
        new_paid = invoice.amount_paid_kes + amount
        new_balance = invoice.total_kes - new_paid
        new_status = InvoiceStatus.PARTIAL.value if new_balance > 0 else InvoiceStatus.PAID.value
        paid_date = datetime.now(timezone.utc) if new_balance <= 0 else None

        result = await self.collection.update_one(
            {"_id": ObjectId(invoice_id)},
            {"$set": {
                "amount_paid_kes": new_paid, "balance_due_kes": new_balance,
                "status": new_status, "paid_date": paid_date,
                "updated_at": datetime.now(timezone.utc),
            }, "$push": {"payment_ids": payment_id}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Invoice not found")

        await self.db.customers.update_one(
            {"_id": ObjectId(invoice.customer_id)},
            {"$inc": {"outstanding_balance": -amount},
             "$set": {"last_payment_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
        )
        return await self.get_by_id(invoice_id)

    async def get_overdue_invoices(self) -> List[InvoiceInDB]:
        query = {
            "status": {"$in": ["sent", "partial", "viewed"]},
            "due_date": {"$lt": datetime.now(timezone.utc)},
        }
        cursor = self.collection.find(query)
        invoices = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            invoices.append(InvoiceInDB(**doc))
        return invoices