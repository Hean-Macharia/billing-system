from datetime import datetime

from pydantic import BaseModel


class InvoiceCreate(BaseModel):
    customer_id: str
    subscription_id: str
    amount: float
    due_date: datetime