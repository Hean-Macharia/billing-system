from datetime import datetime, timezone


def subscription_document(
    subscription_id: str,
    customer_id: str,
    package_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "subscription_id": subscription_id,
        "customer_id": customer_id,
        "package_id": package_id,
        "status": "active",
        "start_date": start_date,
        "end_date": end_date,
        "auto_renew": False,
        "created_at": now,
        "updated_at": now,
    }