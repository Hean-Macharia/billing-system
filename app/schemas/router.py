from pydantic import BaseModel, Field


class RouterCreate(BaseModel):
    name: str
    host: str
    username: str
    password: str
    port: int = Field(default=8728, gt=0, lt=65536)


class RouterUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    username: str | None = None
    password: str | None = None
    port: int | None = None
    status: str | None = None