"""Support ticket model.

A ticket belongs to exactly one customer and holds a simple threaded
message list (customer messages and staff replies interleaved, oldest
first). Kept intentionally simple - one document per ticket, messages
embedded rather than in a separate collection, since ticket volumes for
an ISP this size don't need pagination *within* a ticket.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class TicketStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"  # waiting on the customer
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, Enum):
    BILLING = "billing"
    CONNECTIVITY = "connectivity"
    INSTALLATION = "installation"
    ACCOUNT = "account"
    OTHER = "other"


class TicketMessage(BaseModel):
    sender_role: str  # "customer" or a staff UserRole value
    sender_id: str
    sender_name: str
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Ticket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(alias="_id", default=None)
    ticket_number: str  # e.g. TKT-000123
    customer_id: str
    subject: str
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    assigned_to: Optional[str] = None  # staff user id
    messages: List[TicketMessage] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
