from datetime import datetime

from pydantic import BaseModel


class SubscriptionCreate(BaseModel):
    customer_id: str
    package_id: str
    start_date: datetime
    end_date: datetime
    auto_renew: bool = False


class SubscriptionUpdate(BaseModel):
    status: str | None = None
    auto_renew: bool | None = None