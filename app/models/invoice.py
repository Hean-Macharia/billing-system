from datetime import datetime, timezone


def invoice_document(
    invoice_id: str,
    customer_id: str,
    subscription_id: str,
    amount: float,
    due_date: datetime,
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_id,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "amount": amount,
        "amount_paid": 0,
        "balance": amount,
        "currency": "KES",
        "status": "unpaid",
        "due_date": due_date,
        "created_at": now,
        "updated_at": now,
    }