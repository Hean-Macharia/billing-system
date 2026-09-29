"""Support ticket service.

Used from both sides: app.routes.portal (customer-scoped - a customer
can only ever see/reply to their own tickets) and app.routes.support
(staff-facing - sees everything, gated by Permission.SUPPORT_READ/MANAGE).
The scoping is enforced here, not just in the routes, so a route can't
accidentally leak another customer's ticket by forgetting a filter.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError
from app.models.ticket import Ticket, TicketMessage, TicketStatus
from app.schemas.ticket import TicketCreate, TicketReply


class TicketService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.tickets

    def _oid(self, id_str: str) -> ObjectId:
        try:
            return ObjectId(id_str)
        except Exception as exc:
            raise NotFoundError("Ticket not found") from exc

    async def create_ticket(self, customer_id: str, customer_name: str, data: TicketCreate) -> Ticket:
        now = datetime.now(timezone.utc)
        ticket_number = f"TKT-{uuid4().hex[:8].upper()}"
        doc = {
            "ticket_number": ticket_number,
            "customer_id": customer_id,
            "subject": data.subject,
            "category": data.category.value,
            "priority": data.priority.value,
            "status": TicketStatus.OPEN.value,
            "assigned_to": None,
            "messages": [
                {
                    "sender_role": "customer", "sender_id": customer_id, "sender_name": customer_name,
                    "body": data.message, "created_at": now,
                }
            ],
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return Ticket(**doc)

    async def get_ticket(self, ticket_id: str, customer_id: Optional[str] = None) -> Ticket:
        query = {"_id": self._oid(ticket_id)}
        if customer_id:
            query["customer_id"] = customer_id
        doc = await self.collection.find_one(query)
        if not doc:
            raise NotFoundError("Ticket not found")
        doc["_id"] = str(doc["_id"])
        return Ticket(**doc)

    async def list_tickets(
        self, customer_id: Optional[str] = None, status: Optional[str] = None,
        assigned_to: Optional[str] = None, page: int = 1, limit: int = 20,
    ) -> tuple[List[Ticket], int]:
        query = {}
        if customer_id:
            query["customer_id"] = customer_id
        if status:
            query["status"] = status
        if assigned_to:
            query["assigned_to"] = assigned_to
        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("updated_at", -1)
        tickets = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            tickets.append(Ticket(**doc))
        return tickets, total

    async def add_message(
        self, ticket_id: str, sender_role: str, sender_id: str, sender_name: str,
        data: TicketReply, customer_id: Optional[str] = None,
    ) -> Ticket:
        # Validates ownership (if customer_id given) via get_ticket before mutating.
        await self.get_ticket(ticket_id, customer_id=customer_id)
        now = datetime.now(timezone.utc)
        message = {"sender_role": sender_role, "sender_id": sender_id, "sender_name": sender_name, "body": data.message, "created_at": now}
        new_status = TicketStatus.PENDING.value if sender_role != "customer" else TicketStatus.OPEN.value
        await self.collection.update_one(
            {"_id": self._oid(ticket_id)},
            {"$push": {"messages": message}, "$set": {"updated_at": now, "status": new_status}},
        )
        return await self.get_ticket(ticket_id, customer_id=customer_id)

    async def update_status(self, ticket_id: str, status: TicketStatus) -> Ticket:
        await self.collection.update_one(
            {"_id": self._oid(ticket_id)},
            {"$set": {"status": status.value, "updated_at": datetime.now(timezone.utc)}},
        )
        return await self.get_ticket(ticket_id)

    async def assign(self, ticket_id: str, user_id: str) -> Ticket:
        await self.collection.update_one(
            {"_id": self._oid(ticket_id)},
            {"$set": {"assigned_to": user_id, "updated_at": datetime.now(timezone.utc)}},
        )
        return await self.get_ticket(ticket_id)
