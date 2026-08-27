"""
M-Pesa business logic: STK Push, callback, idempotency, settlement.

Phase 5 responsibilities:
- Initiate STK Push via Daraja
- Receive and idempotently process callbacks
- Record Payment on success
- Settle Invoice
- Renew/Activate Subscription
- Reconcile pending transactions
"""
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings  # <-- added for credentials
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.mpesa.daraja_client import DarajaClient
from app.models.mpesa_transaction import MpesaTransactionInDB, MpesaTransactionStatus
from app.models.payment import PaymentMethod, PaymentStatus
from app.schemas.mpesa import StkPushRequest
from app.schemas.payment import PaymentCreate
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService
from app.services.subscription_service import SubscriptionService

logger = get_logger(__name__)


class MpesaService:
    """M-Pesa service layer with full reconciliation."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.mpesa_transactions

        # Initialize Daraja client with settings from config
        self.daraja = DarajaClient(
            consumer_key=settings.mpesa_consumer_key,
            consumer_secret=settings.mpesa_consumer_secret,
            shortcode=settings.mpesa_shortcode,
            passkey=settings.mpesa_passkey,
            callback_url=settings.mpesa_callback_url,
            environment=settings.mpesa_environment,
        )

    # ── STK PUSH INITIATION ──

    async def initiate_stk_push(self, data: StkPushRequest, created_by: Optional[str] = None) -> MpesaTransactionInDB:
        """Initiate STK Push and store transaction record."""
        # Validate customer exists
        customer = await self.db.customers.find_one({"_id": ObjectId(data.customer_id)})
        if not customer:
            raise NotFoundError("Customer not found")

        # Validate invoice if provided
        if data.invoice_id:
            inv = await self.db.invoices.find_one({"_id": ObjectId(data.invoice_id)})
            if not inv:
                raise NotFoundError("Invoice not found")
            if inv.get("status") == "paid":
                raise ConflictError("Invoice already paid")

        # Create pending transaction record BEFORE calling Safaricom
        now = datetime.now(timezone.utc)
        doc = {
            "transaction_type": "stk_push",
            "customer_id": data.customer_id,
            "invoice_id": data.invoice_id,
            "subscription_id": data.subscription_id,
            "amount": data.amount,
            "phone_number": data.phone_number,
            "account_reference": data.account_reference,
            "transaction_desc": data.transaction_desc,
            "status": MpesaTransactionStatus.PENDING.value,
            "callback_received": False,
            "settled": False,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        tx = MpesaTransactionInDB(**doc)

        try:
            # Call Safaricom Daraja API
            resp = self.daraja.initiate_stk_push(
                phone_number=data.phone_number,
                amount=data.amount,
                account_reference=data.account_reference,
                transaction_desc=data.transaction_desc,
            )

            # Update record with Safaricom IDs
            await self.collection.update_one(
                {"_id": ObjectId(tx.id)},
                {
                    "$set": {
                        "merchant_request_id": resp.get("MerchantRequestID"),
                        "checkout_request_id": resp.get("CheckoutRequestID"),
                        "status": MpesaTransactionStatus.PROCESSING.value,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            tx.merchant_request_id = resp.get("MerchantRequestID")
            tx.checkout_request_id = resp.get("CheckoutRequestID")
            tx.status = MpesaTransactionStatus.PROCESSING
            logger.info(f"STK Push initiated: {tx.checkout_request_id} for customer {data.customer_id}")
            return tx

        except Exception as exc:
            # Mark as failed if Daraja call fails
            await self.collection.update_one(
                {"_id": ObjectId(tx.id)},
                {
                    "$set": {
                        "status": MpesaTransactionStatus.FAILED.value,
                        "result_desc": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            logger.error(f"STK Push initiation failed: {exc}")
            raise ValidationError(f"Failed to initiate M-Pesa payment: {exc}")

    # ── CALLBACK PROCESSING (IDEMPOTENT) ──

    async def process_callback(self, body: dict) -> MpesaTransactionInDB:
        """Process Safaricom STK callback. Fully idempotent.

        Args:
            body: Raw JSON body from Safaricom callback.

        Returns:
            Updated MpesaTransactionInDB
        """
        stk_callback = body.get("Body", {}).get("stkCallback", {})
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        result_code = stk_callback.get("ResultCode")
        result_desc = stk_callback.get("ResultDesc", "")

        if not checkout_request_id:
            raise ValidationError("Missing CheckoutRequestID in callback")

        # Find transaction by checkout_request_id
        doc = await self.collection.find_one({"checkout_request_id": checkout_request_id})
        if not doc:
            logger.warning(f"Callback for unknown CheckoutRequestID: {checkout_request_id}")
            raise NotFoundError("Transaction not found for this checkout request")

        tx_id = str(doc["_id"])

        # ── IDEMPOTENCY CHECK ──
        if doc.get("callback_received"):
            logger.info(f"Duplicate callback ignored for {checkout_request_id}")
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)

        # Extract metadata on success
        mpesa_receipt = None
        mpesa_date = None
        phone_number = doc.get("phone_number")
        amount = doc.get("amount", 0)

        if result_code == 0 and stk_callback.get("CallbackMetadata"):
            items = stk_callback["CallbackMetadata"].get("Item", [])
            for item in items:
                name = item.get("Name")
                value = item.get("Value")
                if name == "MpesaReceiptNumber":
                    mpesa_receipt = value
                elif name == "TransactionDate":
                    mpesa_date = str(value) if value else None
                elif name == "PhoneNumber":
                    phone_number = str(value) if value else phone_number
                elif name == "Amount":
                    amount = float(value) if value else amount

        # Determine status
        status = MpesaTransactionStatus.SUCCESS if result_code == 0 else MpesaTransactionStatus.FAILED
        if result_code is not None and result_code != 0:
            # Common result codes: 1=cancelled, 1032=timeout, 1037=cancelled
            if result_code in (1032, 1037):
                status = MpesaTransactionStatus.CANCELLED
            elif result_code == 1032:
                status = MpesaTransactionStatus.TIMEOUT

        now = datetime.now(timezone.utc)

        # Update transaction record
        await self.collection.update_one(
            {"_id": ObjectId(tx_id)},
            {
                "$set": {
                    "status": status.value,
                    "result_code": result_code,
                    "result_desc": result_desc,
                    "mpesa_receipt_number": mpesa_receipt,
                    "mpesa_transaction_date": mpesa_date,
                    "phone_number": phone_number,
                    "amount": amount,
                    "callback_received": True,
                    "callback_payload": body,
                    "updated_at": now,
                }
            },
        )

        logger.info(f"Callback processed: {checkout_request_id} -> {status.value} (Receipt: {mpesa_receipt})")

        # ── SETTLEMENT: Payment -> Invoice -> Subscription ──
        if status == MpesaTransactionStatus.SUCCESS:
            await self._settle_transaction(tx_id, doc, amount, mpesa_receipt, phone_number)

        return await self.get_by_id(tx_id)

    async def _settle_transaction(
        self,
        tx_id: str,
        tx_doc: dict,
        amount: float,
        mpesa_receipt: Optional[str],
        phone_number: Optional[str],
    ) -> None:
        """Create payment, settle invoice, activate subscription."""
        try:
            customer_id = tx_doc["customer_id"]
            invoice_id = tx_doc.get("invoice_id")
            subscription_id = tx_doc.get("subscription_id")

            # 1. Create Payment record
            payment_data = PaymentCreate(
                customer_id=customer_id,
                invoice_id=invoice_id,
                subscription_id=subscription_id,
                amount_kes=amount,
                payment_method=PaymentMethod.MPESA,
                mpesa_phone_number=phone_number,
                mpesa_receipt_number=mpesa_receipt,
                notes=f"M-Pesa STK Push | Receipt: {mpesa_receipt}",
            )
            payment_service = PaymentService(self.db)
            payment = await payment_service.create(payment_data, created_by="system_mpesa")

            # 2. Confirm payment (triggers invoice application in PaymentService)
            payment = await payment_service.confirm_payment(payment.id, invoice_id=invoice_id)

            # 3. Update subscription to active if exists
            if subscription_id:
                sub_service = SubscriptionService(self.db)
                await self.db.subscriptions.update_one(
                    {"_id": ObjectId(subscription_id)},
                    {
                        "$set": {
                            "status": "active",
                            "last_payment_date": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                # Extend next billing date if monthly
                sub = await self.db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
                if sub and sub.get("billing_cycle") == "monthly":
                    next_bill = datetime.now(timezone.utc) + timedelta(days=30)
                    await self.db.subscriptions.update_one(
                        {"_id": ObjectId(subscription_id)},
                        {"$set": {"next_billing_date": next_bill}},
                    )

            # 4. Update customer balance
            await self.db.customers.update_one(
                {"_id": ObjectId(customer_id)},
                {
                    "$inc": {"total_paid_kes": amount},
                    "$set": {
                        "status": "active",
                        "last_payment_date": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    },
                },
            )

            # 5. Mark transaction as settled
            await self.collection.update_one(
                {"_id": ObjectId(tx_id)},
                {
                    "$set": {
                        "payment_id": payment.id,
                        "settled": True,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            logger.info(f"Transaction {tx_id} settled: Payment={payment.id}, Invoice={invoice_id}, Sub={subscription_id}")

        except Exception as exc:
            logger.error(f"Settlement failed for tx {tx_id}: {exc}")
            await self.collection.update_one(
                {"_id": ObjectId(tx_id)},
                {
                    "$set": {
                        "settled": False,
                        "settlement_error": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

    # ── QUERY & RECONCILIATION ──

    async def query_stk_status(self, checkout_request_id: str) -> MpesaTransactionInDB:
        """Query Safaricom for status of a pending STK transaction."""
        doc = await self.collection.find_one({"checkout_request_id": checkout_request_id})
        if not doc:
            raise NotFoundError("STK request not found")

        # Call Daraja query API
        try:
            resp = self.daraja.query_stk_status(checkout_request_id)
            result_code = resp.get("ResultCode")
            result_desc = resp.get("ResultDesc", "")

            # If we got a definitive result, process it like a callback
            if result_code is not None and not doc.get("callback_received"):
                # Build synthetic callback body
                synthetic_body = {
                    "Body": {
                        "stkCallback": {
                            "CheckoutRequestID": checkout_request_id,
                            "ResultCode": result_code,
                            "ResultDesc": result_desc,
                        }
                    }
                }
                # Add metadata if success
                if result_code == 0 and resp.get("CallbackMetadata"):
                    synthetic_body["Body"]["stkCallback"]["CallbackMetadata"] = resp["CallbackMetadata"]

                return await self.process_callback(synthetic_body)

        except Exception as exc:
            logger.warning(f"STK query failed for {checkout_request_id}: {exc}")

        doc["_id"] = str(doc["_id"])
        return MpesaTransactionInDB(**doc)

    async def reconcile_pending(self, max_age_hours: int = 24) -> List[MpesaTransactionInDB]:
        """Batch reconcile pending transactions older than N hours.

        Returns:
            List of transactions that were updated.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cursor = self.collection.find({
            "status": {"$in": [MpesaTransactionStatus.PENDING.value, MpesaTransactionStatus.PROCESSING.value]},
            "created_at": {"$lte": cutoff},
            "callback_received": False,
        })

        updated = []
        async for doc in cursor:
            checkout_id = doc.get("checkout_request_id")
            if not checkout_id:
                continue
            try:
                tx = await self.query_stk_status(checkout_id)
                updated.append(tx)
            except Exception as exc:
                logger.error(f"Reconciliation failed for {checkout_id}: {exc}")
        return updated

    # ── READ OPERATIONS ──

    async def get_by_id(self, tx_id: str) -> MpesaTransactionInDB:
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(tx_id)})
        except InvalidId:
            raise NotFoundError("Invalid transaction ID")
        if not doc:
            raise NotFoundError("M-Pesa transaction not found")
        doc["_id"] = str(doc["_id"])
        return MpesaTransactionInDB(**doc)

    async def get_by_checkout_id(self, checkout_request_id: str) -> MpesaTransactionInDB:
        doc = await self.collection.find_one({"checkout_request_id": checkout_request_id})
        if not doc:
            raise NotFoundError("Transaction not found")
        doc["_id"] = str(doc["_id"])
        return MpesaTransactionInDB(**doc)

    async def list_transactions(
        self,
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        invoice_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[List[MpesaTransactionInDB], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if status:
            query["status"] = status
        if invoice_id:
            query["invoice_id"] = invoice_id

        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)

        transactions = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            transactions.append(MpesaTransactionInDB(**doc))
        return transactions, total