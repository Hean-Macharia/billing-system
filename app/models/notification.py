"""Notification model.

Every notification the system ever tries to send is logged here first,
before any delivery attempt - so the log itself is never lost even if
SMS/email delivery fails or isn't configured at all. This is also what
powers the customer portal's "notifications" list and the admin's
delivery audit trail.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    INVOICE_GENERATED = "invoice_generated"
    INVOICE_OVERDUE = "invoice_overdue"
    PAYMENT_RECEIVED = "payment_received"
    SERVICE_SUSPENDED = "service_suspended"
    SERVICE_RESTORED = "service_restored"
    VOUCHER_PURCHASED = "voucher_purchased"
    TICKET_UPDATE = "ticket_update"
    GENERIC = "generic"


class NotificationChannel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    LOG_ONLY = "log_only"  # recorded but no external channel configured/attempted


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. customer has no phone on file


class Notification(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    customer_id: Optional[str] = None  # None for non-customer recipients (e.g. hotspot walk-up buyers)
    phone: Optional[str] = None
    notification_type: NotificationType = NotificationType.GENERIC
    channel: NotificationChannel = NotificationChannel.LOG_ONLY
    status: NotificationStatus = NotificationStatus.SKIPPED
    subject: str
    body: str
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
