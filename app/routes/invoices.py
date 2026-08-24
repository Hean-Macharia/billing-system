from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_database
from app.core.security import get_current_user
from app.models.invoice import invoice_document
from app.schemas.invoice import InvoiceCreate


router = APIRouter(
    prefix="/api/v1/invoices",
    tags=["Invoices"],
)


@router.post("/")
async def create_invoice(
    data: InvoiceCreate,
    current_user=Depends(get_current_user),
):

    db = get_database()

    customer = await db.customers.find_one(
        {"customer_id": data.customer_id}
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    invoice_id = (
        f"INV-{uuid4().hex[:8].upper()}"
    )

    document = invoice_document(
        invoice_id=invoice_id,
        customer_id=data.customer_id,
        subscription_id=data.subscription_id,
        amount=data.amount,
        due_date=data.due_date,
    )

    await db.invoices.insert_one(document)

    document.pop("_id", None)

    return document


@router.get("/")
async def get_invoices(
    current_user=Depends(get_current_user),
):

    db = get_database()

    invoices = []

    cursor = db.invoices.find({})

    async for invoice in cursor:
        invoice.pop("_id", None)
        invoices.append(invoice)

    return {
        "count": len(invoices),
        "invoices": invoices,
    }


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    current_user=Depends(get_current_user),
):

    db = get_database()

    invoice = await db.invoices.find_one(
        {"invoice_id": invoice_id}
    )

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found",
        )

    invoice.pop("_id", None)

    return invoice