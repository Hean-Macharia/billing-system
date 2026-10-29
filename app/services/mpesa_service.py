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
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.core.config import settings  # <-- added for credentials
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.mpesa.daraja_client import DarajaClient
from app.models.mpesa_transaction import MpesaTransactionInDB, MpesaTransactionStatus
from app.models.payment import PaymentMethod, PaymentStatus
from app.schemas.mpesa import StkPushRequest
from app.schemas.payment import PaymentCreate
from app.services.payment_service import PaymentService

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
        """Verify and process a Safaricom callback against Daraja's status API.

        Args:
            body: Raw JSON body from Safaricom callback.

        Returns:
            Updated MpesaTransactionInDB
        """
        if not isinstance(body, dict):
            raise ValidationError("Invalid M-Pesa callback")
        callback_body = body.get("Body")
        stk_callback = callback_body.get("stkCallback") if isinstance(callback_body, dict) else None
        if not isinstance(stk_callback, dict):
            raise ValidationError("Invalid M-Pesa callback")
        checkout_request_id = stk_callback.get("CheckoutRequestID")

        if not isinstance(checkout_request_id, str) or not checkout_request_id.strip():
            raise ValidationError("Missing CheckoutRequestID in callback")

        doc = await self.collection.find_one({"checkout_request_id": checkout_request_id})
        if not doc:
            logger.warning("Callback for unknown checkout request")
            raise NotFoundError("Transaction not found for this checkout request")

        tx_id = str(doc["_id"])

        # ── IDEMPOTENCY CHECK ──
        if doc.get("callback_received"):
            if (
                doc.get("status") == MpesaTransactionStatus.SUCCESS.value
                and not doc.get("settled")
                and not doc.get("settlement_review_required")
            ):
                return await self._settle_verified_success(doc)
            logger.info("Duplicate M-Pesa callback ignored")
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)
        if doc.get("settlement_review_required"):
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)

        provider_result = await self._query_provider_status(checkout_request_id)
        if provider_result is None:
            await self.collection.update_one(
                {
                    "_id": ObjectId(tx_id),
                    "callback_received": {"$ne": True},
                    "settlement_review_required": {"$ne": True},
                },
                {
                    "$set": {
                        "callback_verification_pending": True,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            doc["_id"] = tx_id
            doc["callback_verification_pending"] = True
            return MpesaTransactionInDB(**doc)

        return await self._apply_provider_result(
            doc,
            provider_result,
            callback_metadata=stk_callback.get("CallbackMetadata"),
        )

    async def _query_provider_status(self, checkout_request_id: str) -> Optional[dict]:
        """Return a status response confirmed by Daraja for this checkout."""
        try:
            response = self.daraja.query_stk_status(checkout_request_id)
        except Exception as exc:
            logger.warning(
                "M-Pesa provider status verification unavailable: %s",
                type(exc).__name__,
            )
            return None

        if (
            not isinstance(response, dict)
            or response.get("CheckoutRequestID") != checkout_request_id
            or self._parse_result_code(response.get("ResultCode")) is None
        ):
            logger.warning("M-Pesa provider returned an incomplete status verification response")
            return None
        return response

    @staticmethod
    def _parse_result_code(value: object) -> Optional[int]:
        if type(value) is int:
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        return None

    async def _settle_verified_success(self, doc: dict) -> MpesaTransactionInDB:
        """Claim and retry settlement for a provider-confirmed successful payment."""
        tx_id = str(doc["_id"])
        now = datetime.now(timezone.utc)
        claim = await self.collection.find_one_and_update(
            {
                "_id": ObjectId(tx_id),
                "status": MpesaTransactionStatus.SUCCESS.value,
                "settled": {"$ne": True},
                "settlement_review_required": {"$ne": True},
                "$or": [
                    {"settlement_status": {"$ne": "processing"}},
                    {
                        "settlement_status": "processing",
                        "settlement_started_at": {"$lte": now - timedelta(minutes=5)},
                    },
                ],
            },
            {
                "$set": {
                    "settlement_status": "processing",
                    "settlement_started_at": now,
                    "updated_at": now,
                },
                "$unset": {"settlement_error": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not claim:
            return await self.get_by_id(tx_id)

        claim["_id"] = str(claim["_id"])
        try:
            if claim.get("transaction_type") == "hotspot_purchase":
                await self._settle_hotspot_purchase(
                    tx_id,
                    claim,
                    claim["amount"],
                    claim.get("mpesa_receipt_number"),
                    claim["phone_number"],
                )
            else:
                await self._settle_transaction(
                    tx_id,
                    claim,
                    claim["amount"],
                    claim.get("mpesa_receipt_number"),
                    claim["phone_number"],
                )
        except Exception as exc:
            logger.error("M-Pesa settlement failed for tx %s: %s", tx_id, exc)
            await self.collection.update_one(
                {"_id": ObjectId(tx_id), "settlement_status": "processing"},
                {
                    "$set": {
                        "settled": False,
                        "settlement_status": "failed",
                        "settlement_error": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
        else:
            await self.collection.update_one(
                {"_id": ObjectId(tx_id), "settlement_status": "processing"},
                {
                    "$set": {
                        "settled": True,
                        "settlement_status": "completed",
                        "settlement_error": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

        return await self.get_by_id(tx_id)

    async def _apply_provider_result(
        self,
        doc: dict,
        provider_result: dict,
        callback_metadata: Optional[dict] = None,
    ) -> MpesaTransactionInDB:
        """Apply a provider-verified result once, using the initiated amount."""
        tx_id = str(doc["_id"])
        if doc.get("settlement_review_required"):
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)

        checkout_request_id = doc.get("checkout_request_id")
        if provider_result.get("CheckoutRequestID") != checkout_request_id:
            logger.warning("M-Pesa status response did not match the stored checkout")
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)

        result_code = self._parse_result_code(provider_result.get("ResultCode"))
        if result_code is None:
            doc["_id"] = tx_id
            return MpesaTransactionInDB(**doc)

        if result_code == 0:
            status = MpesaTransactionStatus.SUCCESS
        elif result_code in (1032, 1037):
            status = MpesaTransactionStatus.CANCELLED
        else:
            status = MpesaTransactionStatus.FAILED
        amount = doc.get("amount", 0)
        mpesa_receipt = None
        mpesa_date = None

        metadata = (
            callback_metadata
            if callback_metadata is not None
            else provider_result.get("CallbackMetadata")
        )
        if status == MpesaTransactionStatus.SUCCESS and isinstance(metadata, dict):
            items = metadata.get("Item", [])
            if isinstance(items, list):
                values = {
                    item.get("Name"): item.get("Value")
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("Name"), str)
                }
                reported_amount = values.get("Amount")
                amount_matches = True
                if reported_amount is not None:
                    try:
                        amount_matches = Decimal(str(reported_amount)) == Decimal(str(amount))
                    except (InvalidOperation, ValueError):
                        amount_matches = False
                if not amount_matches:
                    logger.warning("Verified M-Pesa callback metadata requires settlement review")
                    await self.collection.update_one(
                        {"_id": ObjectId(tx_id), "callback_received": {"$ne": True}},
                        {
                            "$set": {
                                "settlement_review_required": True,
                                "callback_verification_pending": False,
                                "updated_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    doc["_id"] = tx_id
                    doc["settlement_review_required"] = True
                    doc["callback_verification_pending"] = False
                    return MpesaTransactionInDB(**doc)
                receipt = values.get("MpesaReceiptNumber")
                mpesa_receipt = str(receipt) if receipt is not None else None
                transaction_date = values.get("TransactionDate")
                mpesa_date = str(transaction_date) if transaction_date is not None else None

        now = datetime.now(timezone.utc)
        updated_doc = await self.collection.find_one_and_update(
            {
                "_id": ObjectId(tx_id),
                "callback_received": {"$ne": True},
            },
            {
                "$set": {
                    "status": status.value,
                    "result_code": result_code,
                    "result_desc": provider_result.get("ResultDesc", ""),
                    "mpesa_receipt_number": mpesa_receipt,
                    "mpesa_transaction_date": mpesa_date,
                    "callback_received": True,
                    "callback_verification_pending": False,
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated_doc:
            latest_doc = await self.collection.find_one({"_id": ObjectId(tx_id)})
            if not latest_doc:
                raise NotFoundError("Transaction not found for this checkout request")
            latest_doc["_id"] = tx_id
            return MpesaTransactionInDB(**latest_doc)

        logger.info("M-Pesa provider result applied: status=%s", status.value)
        if status == MpesaTransactionStatus.SUCCESS:
            return await self._settle_verified_success(updated_doc)

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
            transaction_id = f"MPESA-{tx_id}"

            payment_service = PaymentService(self.db)
            existing_payment = await self.db.payments.find_one({"transaction_id": transaction_id})
            if existing_payment:
                payment = await payment_service.get_by_id(str(existing_payment["_id"]))
            else:
                payment_data = PaymentCreate(
                    customer_id=customer_id,
                    invoice_id=invoice_id,
                    subscription_id=subscription_id,
                    amount_kes=amount,
                    payment_method=PaymentMethod.MPESA,
                    mpesa_phone_number=phone_number,
                    mpesa_receipt_number=mpesa_receipt,
                    notes=f"M-Pesa STK Push | Receipt: {mpesa_receipt}",
                    transaction_id=transaction_id,
                )
                try:
                    payment = await payment_service.create(payment_data, created_by="system_mpesa")
                except Exception:
                    existing_payment = await self.db.payments.find_one({"transaction_id": transaction_id})
                    if not existing_payment:
                        raise
                    payment = await payment_service.get_by_id(str(existing_payment["_id"]))

            # 2. Confirm payment (triggers invoice application in PaymentService)
            payment = await payment_service.confirm_payment(payment.id, invoice_id=invoice_id)

            # 3. Update subscription to active if exists
            if subscription_id:
                sub = await self.db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
                subscription_update = {
                    "$set": {
                        "status": "active",
                        "last_payment_date": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$addToSet": {"mpesa_settled_transaction_ids": tx_id},
                }
                if sub and sub.get("billing_cycle") == "monthly":
                    subscription_update["$set"]["next_billing_date"] = (
                        datetime.now(timezone.utc) + timedelta(days=30)
                    )
                await self.db.subscriptions.update_one(
                    {
                        "_id": ObjectId(subscription_id),
                        "mpesa_settled_transaction_ids": {"$ne": tx_id},
                    },
                    subscription_update,
                )

            # 4. Update customer balance. Does NOT blindly reactivate the
            # customer here - a payment can settle one invoice while
            # another stays unpaid, in which case they must stay
            # suspended. AutomationService.try_restore_customer (called
            # right after this method returns) is the single source of
            # truth for whether restoration is actually warranted.
            await self.db.customers.update_one(
                {
                    "_id": ObjectId(customer_id),
                    "mpesa_settled_transaction_ids": {"$ne": tx_id},
                },
                {
                    "$inc": {"total_paid_kes": amount},
                    "$addToSet": {"mpesa_settled_transaction_ids": tx_id},
                    "$set": {
                        "last_payment_date": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    },
                },
            )

            # 5. Record the payment association; completion is recorded by
            # _settle_verified_success after all settlement effects finish.
            await self.collection.update_one(
                {"_id": ObjectId(tx_id)},
                {
                    "$set": {
                        "payment_id": payment.id,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            logger.info("M-Pesa settlement effects applied: tx=%s", tx_id)

            # 6. Restore service if this payment cleared everything the
            # customer owed (checks ALL their invoices, not just this
            # one - see the note on step 4 above).
            try:
                from app.services.automation_service import AutomationService
                await AutomationService(self.db).try_restore_customer(customer_id)
            except Exception as restore_exc:  # noqa: BLE001
                logger.warning(f"Post-payment restoration check failed for customer {customer_id}: {restore_exc}")

        except Exception:
            raise

    # ── HOTSPOT SELF-SERVICE PURCHASE (Phase 11) ──
    #
    # A walk-up HotSpot buyer scanning the captive portal isn't a
    # registered Customer at all, so this deliberately does NOT reuse
    # initiate_stk_push/_settle_transaction above (both hard-require a
    # real customer_id and an invoice) - it's a parallel, self-contained
    # path through the same mpesa_transactions collection, distinguished
    # by transaction_type="hotspot_purchase" and dispatched to from
    # process_callback.

    async def initiate_hotspot_purchase(
        self, plan_id: str, phone_number: str, device_type: str, device_mac: str
    ) -> MpesaTransactionInDB:
        plan = await self.db.hotspot_plans.find_one({"_id": ObjectId(plan_id)})
        if not plan:
            raise NotFoundError("HotSpot plan not found")
        if not plan.get("is_active", True):
            raise ValidationError("This plan is no longer available")

        now = datetime.now(timezone.utc)
        doc = {
            "transaction_type": "hotspot_purchase",
            "merchant_request_id": None,
            "customer_id": None, "invoice_id": None, "subscription_id": None,
            "hotspot_plan_id": plan_id, "voucher_code": None,
            "device_type": device_type, "device_mac": device_mac.replace("-", ":").upper(),
            "amount": plan["price"], "phone_number": phone_number,
            "account_reference": plan["name"], "transaction_desc": f"HotSpot: {plan['name']}",
            "status": MpesaTransactionStatus.PENDING.value,
            "result_code": None, "result_desc": None,
            "mpesa_receipt_number": None, "mpesa_transaction_date": None,
            "callback_received": False, "callback_payload": None,
            "payment_id": None, "settled": False, "settlement_error": None,
            "created_at": now, "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        tx = MpesaTransactionInDB(**doc)

        try:
            resp = self.daraja.initiate_stk_push(
                phone_number=phone_number, amount=plan["price"],
                account_reference=plan["name"], transaction_desc=f"HotSpot: {plan['name']}",
            )
            await self.collection.update_one(
                {"_id": ObjectId(tx.id)},
                {"$set": {
                    "merchant_request_id": resp.get("MerchantRequestID"),
                    "checkout_request_id": resp.get("CheckoutRequestID"),
                    "status": MpesaTransactionStatus.PROCESSING.value,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            tx.merchant_request_id = resp.get("MerchantRequestID")
            tx.checkout_request_id = resp.get("CheckoutRequestID")
            tx.status = MpesaTransactionStatus.PROCESSING
            logger.info(f"HotSpot purchase STK push initiated: {tx.checkout_request_id} for plan {plan['name']}")
            return tx
        except Exception as exc:
            await self.collection.update_one(
                {"_id": ObjectId(tx.id)},
                {"$set": {"status": MpesaTransactionStatus.FAILED.value, "result_desc": str(exc), "updated_at": datetime.now(timezone.utc)}},
            )
            logger.error(f"HotSpot purchase STK push failed: {exc}")
            raise ValidationError(f"Failed to initiate M-Pesa payment: {exc}")

    async def _settle_hotspot_purchase(self, tx_id: str, doc: dict, amount: float, mpesa_receipt: Optional[str], phone_number: str) -> None:
        """On successful payment: generate ONE active voucher from the
        purchased plan and attach its code to the transaction so the
        captive portal's status-poll endpoint can hand it back."""
        try:
            from app.models.notification import NotificationType
            from app.services.notification_service import NotificationService
            from app.services.voucher_service import VoucherService

            plan_id = doc.get("hotspot_plan_id")
            voucher_service = VoucherService(self.db)
            voucher = await voucher_service.create_hotspot_purchase_voucher(
                purchase_transaction_id=tx_id,
                plan_id=plan_id,
                device_mac=doc.get("device_mac", ""),
                device_type=doc.get("device_type", ""),
            )
            voucher_code = voucher["voucher_code"]

            await self.collection.update_one(
                {"_id": ObjectId(tx_id)},
                {"$set": {"voucher_code": voucher_code, "settled": True, "updated_at": datetime.now(timezone.utc)}},
            )

            await NotificationService(self.db).notify(
                subject="HotSpot voucher purchased",
                body=f"Thank you for your payment of KES {amount:,.2f}. Your HotSpot code is {voucher_code}. Enjoy your connection!",
                phone=phone_number, notification_type=NotificationType.VOUCHER_PURCHASED,
            )
            logger.info("HotSpot purchase settled: transaction=%s", tx_id)
        except Exception:
            raise

    # ── QUERY & RECONCILIATION ──

    async def query_stk_status(self, checkout_request_id: str) -> MpesaTransactionInDB:
        """Query Safaricom for status of a pending STK transaction."""
        doc = await self.collection.find_one({"checkout_request_id": checkout_request_id})
        if not doc:
            raise NotFoundError("STK request not found")

        if doc.get("callback_received"):
            if (
                doc.get("status") == MpesaTransactionStatus.SUCCESS.value
                and not doc.get("settled")
                and not doc.get("settlement_review_required")
            ):
                return await self._settle_verified_success(doc)
            doc["_id"] = str(doc["_id"])
            return MpesaTransactionInDB(**doc)
        if doc.get("settlement_review_required"):
            doc["_id"] = str(doc["_id"])
            return MpesaTransactionInDB(**doc)

        provider_result = await self._query_provider_status(checkout_request_id)
        if provider_result is None:
            doc["_id"] = str(doc["_id"])
            return MpesaTransactionInDB(**doc)
        return await self._apply_provider_result(doc, provider_result)

    async def reconcile_pending(self, max_age_hours: int = 24) -> List[MpesaTransactionInDB]:
        """Batch reconcile pending transactions older than N hours.

        Returns:
            List of transactions that were updated.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        lease_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        cursor = self.collection.find({
            "$or": [
                {
                    "status": {
                        "$in": [
                            MpesaTransactionStatus.PENDING.value,
                            MpesaTransactionStatus.PROCESSING.value,
                        ]
                    },
                    "callback_received": False,
                    "settlement_review_required": {"$ne": True},
                    "$or": [
                        {"created_at": {"$lte": cutoff}},
                        {"callback_verification_pending": True},
                    ],
                },
                {
                    "status": MpesaTransactionStatus.SUCCESS.value,
                    "settled": {"$ne": True},
                    "settlement_review_required": {"$ne": True},
                    "$or": [
                        {"settlement_status": {"$ne": "processing"}},
                        {
                            "settlement_status": "processing",
                            "settlement_started_at": {"$lte": lease_cutoff},
                        },
                    ],
                },
            ],
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