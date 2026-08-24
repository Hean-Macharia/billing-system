from datetime import datetime, timezone


def payment_document(
    payment_id: str,
    customer_id: str,
    amount: float,
    method: str,
    invoice_id: str | None = None,
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "payment_id": payment_id,
        "customer_id": customer_id,
        "invoice_id": invoice_id,
        "amount": amount,
        "currency": "KES",
        "method": method,
        "status": "pending",
        "transaction_id": None,
        "mpesa_receipt": None,
        "phone": None,
        "created_at": now,
        "updated_at": now,
    }