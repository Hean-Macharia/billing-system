from datetime import datetime, timezone


def user_document(
    user_id: str,
    full_name: str,
    email: str,
    password_hash: str,
    role: str = "admin",
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "user_id": user_id,
        "full_name": full_name,
        "email": email.lower(),
        "password_hash": password_hash,
        "role": role,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }