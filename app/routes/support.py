"""Staff-facing support ticket management. Customer-facing ticket routes
live in app.routes.portal - kept separate because the permission model
and the "which tickets can I see" scoping are completely different
(everything here, vs. only-your-own there)."""
from typing import Optional

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.models.user import Permission, UserInDB
from app.schemas.ticket import TicketAssign, TicketReply, TicketStatusUpdate
from app.services.ticket_service import TicketService
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/support", tags=["Support (Staff)"])


@router.get("/tickets", response_model=dict)
async def list_tickets(
    status_filter: Optional[str] = None, customer_id: Optional[str] = None, assigned_to: Optional[str] = None,
    page: int = 1, limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.SUPPORT_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    tickets, total = await service.list_tickets(customer_id=customer_id, status=status_filter, assigned_to=assigned_to, page=page, limit=limit)
    return paginated_response(data=[t.model_dump(by_alias=True) for t in tickets], total=total, page=page, limit=limit)


@router.get("/tickets/{ticket_id}", response_model=dict)
async def get_ticket(
    ticket_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUPPORT_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    ticket = await service.get_ticket(ticket_id)
    return success_response(message="Ticket retrieved", data=ticket.model_dump(by_alias=True))


@router.post("/tickets/{ticket_id}/reply", response_model=dict)
async def reply_ticket(
    ticket_id: str, data: TicketReply,
    current_user: UserInDB = Depends(require_permission(Permission.SUPPORT_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    ticket = await service.add_message(
        ticket_id, sender_role=current_user.role.value, sender_id=str(current_user.id),
        sender_name=current_user.full_name, data=data,
    )
    return success_response(message="Reply added", data=ticket.model_dump(by_alias=True))


@router.patch("/tickets/{ticket_id}/status", response_model=dict)
async def update_ticket_status(
    ticket_id: str, data: TicketStatusUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.SUPPORT_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    ticket = await service.update_status(ticket_id, data.status)
    return success_response(message="Ticket status updated", data=ticket.model_dump(by_alias=True))


@router.patch("/tickets/{ticket_id}/assign", response_model=dict)
async def assign_ticket(
    ticket_id: str, data: TicketAssign,
    current_user: UserInDB = Depends(require_permission(Permission.SUPPORT_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    ticket = await service.assign(ticket_id, data.user_id)
    return success_response(message="Ticket assigned", data=ticket.model_dump(by_alias=True))
