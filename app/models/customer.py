from datetime import datetime, timezone


def customer_document(
    customer_id: str,
    full_name: str,
    phone: str,
    email: str | None = None,
    customer_type: str = "home",
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "customer_id": customer_id,
        "customer_number": customer_id,
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "customer_type": customer_type,
        "status": "active",
        "address": None,
        "location": None,
        "created_at": now,
        "updated_at": now,
    }