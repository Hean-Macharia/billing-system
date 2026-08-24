from datetime import datetime, timezone


async def apply_payment_to_invoice(
    db,
    invoice_id: str,
    amount: float,
):
    invoice = await db.invoices.find_one(
        {"invoice_id": invoice_id}
    )

    if not invoice:
        return None

    current_paid = invoice.get(
        "amount_paid",
        0,
    )

    total_amount = invoice["amount"]

    new_paid = current_paid + amount

    if new_paid >= total_amount:
        status = "paid"
        balance = 0
    else:
        status = "partially_paid"
        balance = total_amount - new_paid

    await db.invoices.update_one(
        {"invoice_id": invoice_id},
        {
            "$set": {
                "amount_paid": new_paid,
                "balance": balance,
                "status": status,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return await db.invoices.find_one(
        {"invoice_id": invoice_id}
    )