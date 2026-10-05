"""Notification service.

Replaces a placeholder stub (send_sms/send_email that just returned
{"status": "simulation"} and was never called from anywhere) with a real
implementation.

Design principle: a notification failure must never break the business
operation that triggered it (an invoice can be generated even if the SMS
about it fails to send). So notify() catches everything internally and
always returns a Notification record rather than raising.

SMS delivery only actually happens if AFRICAS_TALKING_USERNAME and
AFRICAS_TALKING_API_KEY are both set in the environment - there were no
real credentials to test against, so the honest default is "log
everything, attempt SMS only when explicitly configured, degrade to
log-only otherwise" rather than pretending delivery happened.
"""
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import get_logger
from app.models.notification import Notification, NotificationChannel, NotificationStatus, NotificationType

logger = get_logger(__name__)

AFRICAS_TALKING_SMS_URL = "https://api.africastalking.com/version1/messaging"


class NotificationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.notifications

    def _sms_configured(self) -> bool:
        return bool(settings.africas_talking_username and settings.africas_talking_api_key)

    async def _send_sms(self, phone: str, message: str) -> None:
        """Raises on failure - caller (notify()) is responsible for catching."""
        import httpx

        headers = {
            "apiKey": settings.africas_talking_api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"username": settings.africas_talking_username, "to": phone, "message": message}
        if settings.africas_talking_sender_id:
            data["from"] = settings.africas_talking_sender_id

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(AFRICAS_TALKING_SMS_URL, headers=headers, data=data)
            resp.raise_for_status()
            body = resp.json()
            recipients = body.get("SMSMessageData", {}).get("Recipients", [])
            if not recipients or recipients[0].get("statusCode") not in (100, 101):
                raise RuntimeError(f"Africa's Talking rejected the message: {body}")

    async def notify(
        self,
        subject: str,
        body: str,
        customer_id: Optional[str] = None,
        phone: Optional[str] = None,
        notification_type: NotificationType = NotificationType.GENERIC,
    ) -> Notification:
        now = datetime.now(timezone.utc)
        channel = NotificationChannel.LOG_ONLY
        status = NotificationStatus.SKIPPED
        error = None

        if phone and self._sms_configured():
            channel = NotificationChannel.SMS
            try:
                await self._send_sms(phone, body)
                status = NotificationStatus.SENT
            except Exception as exc:  # noqa: BLE001 - never let a notification failure propagate
                status = NotificationStatus.FAILED
                error = str(exc)
                logger.warning(f"SMS notification failed for {phone}: {exc}")
        elif not phone:
            error = "No phone number on file"
        # else: SMS not configured - stays LOG_ONLY/SKIPPED, which is expected, not an error

        doc = {
            "customer_id": customer_id, "phone": phone, "notification_type": notification_type.value,
            "channel": channel.value, "status": status.value, "subject": subject, "body": body,
            "error": error, "created_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return Notification(**doc)

    async def list_for_customer(self, customer_id: str, page: int = 1, limit: int = 20):
        query = {"customer_id": customer_id}
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Notification(**doc))
        return items, total

    async def list_all(self, notification_type: Optional[str] = None, status: Optional[str] = None, page: int = 1, limit: int = 50):
        query = {}
        if notification_type:
            query["notification_type"] = notification_type
        if status:
            query["status"] = status
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Notification(**doc))
        return items, total
