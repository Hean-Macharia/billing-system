from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.ticket import TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.MEDIUM
    message: str = Field(..., min_length=1, max_length=4000)


class TicketReply(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketAssign(BaseModel):
    user_id: str


class TicketMessageResponse(BaseModel):
    sender_role: str
    sender_id: str
    sender_name: str
    body: str
    created_at: datetime


class TicketResponse(BaseModel):
    id: str = Field(alias="_id")
    ticket_number: str
    customer_id: str
    subject: str
    category: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    messages: List[TicketMessageResponse]
    created_at: datetime
    updated_at: datetime
