from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr | None = None
    customer_type: str = "home"


class CustomerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    customer_type: str | None = None
    status: str | None = None


class CustomerResponse(CustomerCreate):
    customer_id: str
    customer_number: str
    status: str