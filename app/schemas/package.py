from pydantic import BaseModel, Field


class PackageCreate(BaseModel):
    name: str
    package_type: str = "home"
    download_speed: int = Field(gt=0)
    upload_speed: int = Field(gt=0)
    price: float = Field(gt=0)
    validity_days: int = Field(gt=0)
    mikrotik_profile: str | None = None
    max_devices: int = Field(default=1, gt=0)


class PackageUpdate(BaseModel):
    name: str | None = None
    download_speed: int | None = None
    upload_speed: int | None = None
    price: float | None = None
    validity_days: int | None = None
    mikrotik_profile: str | None = None
    max_devices: int | None = None
    status: str | None = None