import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.services.invoice_service import InvoiceService
from app.services.mpesa_service import MpesaService
from app.services.payment_service import PaymentService


@pytest.mark.asyncio
async def test_repeated_payment_confirmation_applies_financial_effects_once():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["payment_confirmation_idempotency_test"]
    customer_id = ObjectId()
    invoice_id = ObjectId()
    subscription_id = ObjectId()
    payment_id = ObjectId()
    now = datetime.now(timezone.utc)

    await db.customers.insert_one({
        "_id": customer_id,
        "outstanding_balance": 100,
    })
    await db.invoices.insert_one({
        "_id": invoice_id,
        "invoice_number": "INV-TEST-1",
        "customer_id": str(customer_id),
        "invoice_date": now,
        "due_date": now,
        "status": "sent",
        "total_kes": 100,
        "amount_paid_kes": 0,
        "balance_due_kes": 100,
        "payment_ids": [],
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "total_paid_kes": 0,
        "applied_payment_ids": [],
    })
    await db.payments.insert_one({
        "_id": payment_id,
        "transaction_id": "MPESA-test-1",
        "customer_id": str(customer_id),
        "invoice_id": str(invoice_id),
        "subscription_id": str(subscription_id),
        "amount_kes": 100,
        "payment_method": "mpesa",
        "status": "pending",
        "payment_date": now,
        "created_at": now,
        "updated_at": now,
    })
    service = PaymentService(db)

    await asyncio.gather(
        service.confirm_payment(str(payment_id), invoice_id=str(invoice_id)),
        service.confirm_payment(str(payment_id), invoice_id=str(invoice_id)),
    )

    invoice = await db.invoices.find_one({"_id": invoice_id})
    customer = await db.customers.find_one({"_id": customer_id})
    subscription = await db.subscriptions.find_one({"_id": subscription_id})
    assert invoice["amount_paid_kes"] == 100
    assert invoice["payment_ids"] == [str(payment_id)]
    assert invoice["balance_due_kes"] == 0
    assert customer["outstanding_balance"] == 0
    assert customer["applied_payment_ids"] == [str(payment_id)]
    assert subscription["total_paid_kes"] == 100
    assert subscription["applied_payment_ids"] == [str(payment_id)]
    client.close()


@pytest.mark.asyncio
async def test_concurrent_distinct_payments_are_both_applied_to_invoice():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["concurrent_invoice_payment_test"]
    customer_id = ObjectId()
    invoice_id = ObjectId()
    now = datetime.now(timezone.utc)
    await db.customers.insert_one({"_id": customer_id, "outstanding_balance": 100})
    await db.invoices.insert_one({
        "_id": invoice_id,
        "invoice_number": "INV-TEST-2",
        "customer_id": str(customer_id),
        "invoice_date": now,
        "due_date": now,
        "status": "sent",
        "total_kes": 100,
        "amount_paid_kes": 0,
        "balance_due_kes": 100,
        "payment_ids": [],
    })
    await asyncio.gather(
        InvoiceService(db).apply_payment(str(invoice_id), "payment-a", 50),
        InvoiceService(db).apply_payment(str(invoice_id), "payment-b", 50),
    )

    invoice = await db.invoices.find_one({"_id": invoice_id})
    customer = await db.customers.find_one({"_id": customer_id})
    assert invoice["amount_paid_kes"] == 100
    assert set(invoice["payment_ids"]) == {"payment-a", "payment-b"}
    assert customer["outstanding_balance"] == 0
    assert set(customer["applied_payment_ids"]) == {"payment-a", "payment-b"}
    client.close()


@pytest.mark.asyncio
async def test_m_pesa_settlement_retry_keeps_one_payment_and_financial_application(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_financial_retry_test"]
    customer_id = ObjectId()
    invoice_id = ObjectId()
    subscription_id = ObjectId()
    tx_id = ObjectId()
    now = datetime.now(timezone.utc)
    await db.customers.insert_one({
        "_id": customer_id,
        "outstanding_balance": 100,
        "total_paid_kes": 0,
    })
    await db.invoices.insert_one({
        "_id": invoice_id,
        "invoice_number": "INV-MPESA-1",
        "customer_id": str(customer_id),
        "invoice_date": now,
        "due_date": now,
        "status": "sent",
        "total_kes": 100,
        "amount_paid_kes": 0,
        "balance_due_kes": 100,
        "payment_ids": [],
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "billing_cycle": "monthly",
        "total_paid_kes": 0,
    })
    await db.mpesa_transactions.insert_one({
        "_id": tx_id,
        "status": "success",
        "settled": False,
    })

    async def no_service_restore(_service, _customer_id):
        return False

    from app.services.automation_service import AutomationService

    monkeypatch.setattr(AutomationService, "try_restore_customer", no_service_restore)
    service = MpesaService(db)
    transaction = {
        "_id": str(tx_id),
        "customer_id": str(customer_id),
        "invoice_id": str(invoice_id),
        "subscription_id": str(subscription_id),
    }

    await service._settle_transaction(
        str(tx_id), transaction, 100, "MPESA-RECEIPT-1", "254700000000"
    )
    first_next_billing_date = (
        await db.subscriptions.find_one({"_id": subscription_id})
    )["next_billing_date"]
    await service._settle_transaction(
        str(tx_id), transaction, 100, "MPESA-RECEIPT-1", "254700000000"
    )

    payments = await db.payments.find({"transaction_id": f"MPESA-{tx_id}"}).to_list(2)
    invoice = await db.invoices.find_one({"_id": invoice_id})
    customer = await db.customers.find_one({"_id": customer_id})
    subscription = await db.subscriptions.find_one({"_id": subscription_id})
    assert len(payments) == 1
    assert payments[0]["mpesa_receipt_number"] == "MPESA-RECEIPT-1"
    assert invoice["amount_paid_kes"] == 100
    assert invoice["payment_ids"] == [str(payments[0]["_id"])]
    assert customer["outstanding_balance"] == 0
    assert customer["total_paid_kes"] == 100
    assert subscription["total_paid_kes"] == 100
    assert subscription["next_billing_date"] == first_next_billing_date
    client.close()
