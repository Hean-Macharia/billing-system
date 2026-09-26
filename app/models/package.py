from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId


def package_document(
    package_id: str,
    name: str,
    package_type: str,
    price: float,
    duration_days: int,
    description: Optional[str] = None,
    download_speed: Optional[int] = None,
    upload_speed: Optional[int] = None,
    data_limit_gb: Optional[float] = None,
    mikrotik_profile: Optional[str] = None,
    max_devices: int = 1,
    is_active: bool = True,
):
    """
    Create a MongoDB document for an ISP package.

    package_type:
        - home
        - hotspot
    """

    now = datetime.now(timezone.utc)

    return {
        "_id": ObjectId(),
        "package_id": package_id,
        "name": name,
        "description": description,
        "package_type": package_type,
        "price": price,
        "duration_days": duration_days,
        "download_speed": download_speed,
        "upload_speed": upload_speed,
        "data_limit_gb": data_limit_gb,
        "mikrotik_profile": mikrotik_profile,
        "max_devices": max_devices,
        "status": "active" if is_active else "inactive",
        "is_active": is_active,
        "created_at": now,
        "updated_at": now,
    }