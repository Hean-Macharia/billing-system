"""Customer portal API.

Every route here is scoped to the calling customer via
Depends(get_current_customer) - never a bare "list everything" query.
Login itself reuses POST /api/v1/auth/login unchanged (a customer is just
a User row with role=customer); only self-registration is new here.
"""
import io
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_role
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.models.user import UserInDB, UserRole
from app.schemas.mpesa import StkPushRequest
from app.schemas.portal import PortalRegisterRequest, PortalStkPushRequest
from app.schemas.ticket import TicketCreate, TicketReply
from app.services.mpesa_service import MpesaService
from app.services.portal_service import PortalService
from app.services.ticket_service import TicketService
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/portal", tags=["Customer Portal"])


async def get_current_customer(
    current_user: UserInDB = Depends(require_role(UserRole.CUSTOMER)),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """The authenticated customer's own record - the single choke point
    every portal route resolves scoping through."""
    service = PortalService(db)
    return await service.get_customer_for_user(str(current_user.id))


# ==================================================================== #
# Self-service registration (public)
# ==================================================================== #

@router.post("/auth/register", status_code=503)
async def portal_register(data: PortalRegisterRequest):
    """Keep public activation closed until proof-of-control is available."""
    raise ServiceUnavailableError(
        "Portal activation is temporarily unavailable while secure verification is being set up. "
        "Please contact support for access."
    )


# ==================================================================== #
# Profile / Dashboard
# ==================================================================== #

@router.get("/me", response_model=dict)
async def portal_me(customer: dict = Depends(get_current_customer)):
    customer.pop("user_id", None)
    return success_response(message="Profile retrieved", data=customer)


@router.get("/dashboard", response_model=dict)
async def portal_dashboard(customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    service = PortalService(db)
    return success_response(message="Dashboard retrieved", data=await service.get_dashboard(customer))


# ==================================================================== #
# Subscription
# ==================================================================== #

@router.get("/subscriptions", response_model=dict)
async def portal_subscriptions(customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    subs = []
    async for doc in db.subscriptions.find({"customer_id": customer["_id"]}).sort("created_at", -1):
        plan = await db.service_plans.find_one({"_id": ObjectId(doc["plan_id"])}) if doc.get("plan_id") else None
        doc["_id"] = str(doc["_id"])
        doc["plan_name"] = plan.get("name") if plan else None
        doc["plan_download_speed_mbps"] = plan.get("download_speed_mbps") if plan else None
        doc["plan_upload_speed_mbps"] = plan.get("upload_speed_mbps") if plan else None
        subs.append(doc)
    return success_response(message="Subscriptions retrieved", data=subs)


# ==================================================================== #
# Usage
# ==================================================================== #

@router.get("/usage", response_model=dict)
async def portal_usage(days: int = 30, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    service = PortalService(db)
    days = max(1, min(days, 90))
    return success_response(message="Usage retrieved", data=await service.get_usage(customer, days=days))


# ==================================================================== #
# Notifications
# ==================================================================== #

@router.get("/notifications", response_model=dict)
async def portal_notifications(
    page: int = 1, limit: int = 20, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db),
):
    from app.services.notification_service import NotificationService
    service = NotificationService(db)
    items, total = await service.list_for_customer(customer["_id"], page=page, limit=limit)
    return paginated_response(data=[n.model_dump(by_alias=True) for n in items], total=total, page=page, limit=limit)


# ==================================================================== #
# Invoices
# ==================================================================== #

@router.get("/invoices", response_model=dict)
async def portal_invoices(
    status_filter: str | None = None, page: int = 1, limit: int = 20,
    customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db),
):
    query = {"customer_id": customer["_id"]}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    total = await db.invoices.count_documents(query)
    cursor = db.invoices.find(query).skip(skip).limit(limit).sort("invoice_date", -1)
    invoices = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        invoices.append(doc)
    return paginated_response(data=invoices, total=total, page=page, limit=limit)


@router.get("/invoices/{invoice_id}", response_model=dict)
async def portal_get_invoice(invoice_id: str, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        oid = ObjectId(invoice_id)
    except Exception as exc:
        raise NotFoundError("Invoice not found") from exc
    doc = await db.invoices.find_one({"_id": oid, "customer_id": customer["_id"]})
    if not doc:
        raise NotFoundError("Invoice not found")
    doc["_id"] = str(doc["_id"])
    return success_response(message="Invoice retrieved", data=doc)


# ==================================================================== #
# Payments + M-Pesa + Receipts
# ==================================================================== #

@router.get("/payments", response_model=dict)
async def portal_payments(page: int = 1, limit: int = 20, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    query = {"customer_id": customer["_id"]}
    skip = (page - 1) * limit
    total = await db.payments.count_documents(query)
    cursor = db.payments.find(query).skip(skip).limit(limit).sort("created_at", -1)
    payments = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        payments.append(doc)
    return paginated_response(data=payments, total=total, page=page, limit=limit)


@router.post("/payments/stk-push", response_model=dict, status_code=201)
async def portal_stk_push(
    data: PortalStkPushRequest, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Customer-initiated M-Pesa payment - the invoice-ownership check is
    the whole reason this isn't just a thin wrapper around the admin
    /api/v1/mpesa/stk-push endpoint: without it, any logged-in customer
    could pay (or probe) any invoice in the system by guessing an id."""
    try:
        oid = ObjectId(data.invoice_id)
    except Exception as exc:
        raise NotFoundError("Invoice not found") from exc
    invoice = await db.invoices.find_one({"_id": oid, "customer_id": customer["_id"]})
    if not invoice:
        raise NotFoundError("Invoice not found")
    if invoice.get("status") == "paid":
        raise ConflictError("This invoice is already paid")

    mpesa_service = MpesaService(db)
    txn = await mpesa_service.initiate_stk_push(
        StkPushRequest(
            phone_number=data.phone_number,
            amount=invoice.get("balance_due_kes") or invoice.get("total_kes"),
            account_reference=invoice.get("invoice_number", customer.get("customer_code")),
            transaction_desc=f"Payment for {invoice.get('invoice_number')}",
            customer_id=customer["_id"],
            invoice_id=data.invoice_id,
        )
    )
    return success_response(message="STK push initiated - check your phone", data={"checkout_request_id": txn.checkout_request_id}, status_code=201)


def _build_receipt_pdf(payment: dict, customer: dict) -> bytes:
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    w, h = A5
    c = canvas.Canvas(buf, pagesize=A5)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, h - 20 * mm, "Payment Receipt")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 27 * mm, "DEVZEN CREATIONS")

    c.setFont("Helvetica", 10)
    y = h - 42 * mm
    rows = [
        ("Receipt for", payment.get("mpesa_receipt_number") or str(payment.get("_id"))),
        ("Date", (payment.get("created_at") or datetime.now(timezone.utc)).strftime("%d %b %Y, %H:%M")),
        ("Customer", customer.get("full_name", "")),
        ("Customer code", customer.get("customer_code", "")),
        ("Invoice", payment.get("invoice_number") or "—"),
        ("Method", (payment.get("payment_method") or "").upper()),
        ("Status", (payment.get("status") or "").upper()),
    ]
    for label, value in rows:
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, y, label)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(w - 20 * mm, y, str(value))
        y -= 7 * mm

    y -= 4 * mm
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, "Amount paid")
    c.drawRightString(w - 20 * mm, y, f"KES {payment.get('amount_kes', 0):,.2f}")

    c.setFont("Helvetica", 7)
    c.drawCentredString(w / 2, 14 * mm, "This is a system-generated receipt.")
    c.save()
    buf.seek(0)
    return buf.read()


@router.get("/payments/{payment_id}/receipt")
async def portal_payment_receipt(payment_id: str, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        oid = ObjectId(payment_id)
    except Exception as exc:
        raise NotFoundError("Payment not found") from exc
    payment = await db.payments.find_one({"_id": oid, "customer_id": customer["_id"]})
    if not payment:
        raise NotFoundError("Payment not found")
    if payment.get("status") != "completed":
        raise ValidationError("A receipt is only available for a completed payment")

    pdf_bytes = _build_receipt_pdf(payment, customer)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="receipt_{payment_id}.pdf"'},
    )


# ==================================================================== #
# Support tickets
# ==================================================================== #

@router.post("/support/tickets", response_model=dict, status_code=201)
async def portal_create_ticket(data: TicketCreate, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    service = TicketService(db)
    ticket = await service.create_ticket(customer["_id"], customer.get("full_name", ""), data)
    return success_response(message="Ticket created", data=ticket.model_dump(by_alias=True), status_code=201)


@router.get("/support/tickets", response_model=dict)
async def portal_list_tickets(
    status_filter: str | None = None, page: int = 1, limit: int = 20,
    customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    tickets, total = await service.list_tickets(customer_id=customer["_id"], status=status_filter, page=page, limit=limit)
    return paginated_response(data=[t.model_dump(by_alias=True) for t in tickets], total=total, page=page, limit=limit)


@router.get("/support/tickets/{ticket_id}", response_model=dict)
async def portal_get_ticket(ticket_id: str, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db)):
    service = TicketService(db)
    ticket = await service.get_ticket(ticket_id, customer_id=customer["_id"])
    return success_response(message="Ticket retrieved", data=ticket.model_dump(by_alias=True))


@router.post("/support/tickets/{ticket_id}/reply", response_model=dict)
async def portal_reply_ticket(
    ticket_id: str, data: TicketReply, customer: dict = Depends(get_current_customer), db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = TicketService(db)
    ticket = await service.add_message(
        ticket_id, sender_role="customer", sender_id=customer["_id"], sender_name=customer.get("full_name", ""),
        data=data, customer_id=customer["_id"],
    )
    return success_response(message="Reply added", data=ticket.model_dump(by_alias=True))
