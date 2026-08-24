from datetime import datetime, timezone


def router_document(
    router_id: str,
    name: str,
    host: str,
    username: str,
    password: str,
    port: int = 8728,
) -> dict:

    now = datetime.now(timezone.utc)

    return {
        "router_id": router_id,
        "name": name,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "status": "unknown",
        "created_at": now,
        "updated_at": now,
    }