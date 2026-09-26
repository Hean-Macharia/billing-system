"""Simple package catalog (home/hotspot pricing reference).

Was previously calling an undefined get_database() (NameError on every
request) and building package_document() with kwargs the function didn't
accept (package_id, validity_days) - both fixed. Also fixed: the document
never stored a package_id field at all, so GET/{package_id} could never
have found anything even once the crash was fixed.

Note: this catalog is NOT referenced by Subscriptions - subscriptions
link to app.services.service_plan_service's service_plans collection
(see app/routes/services.py) instead. Keep both if you want a simple
marketing price list here separate from the full billing-engine service
plans, or consolidate onto /api/v1/services if that's redundant for your
use case.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import NotFoundError, ValidationError
from app.models.package import package_document
from app.models.user import Permission, UserInDB
from app.schemas.package import PackageCreate, PackageUpdate
from app.utils.helpers import success_response

router = APIRouter(prefix="/api/v1/packages", tags=["Packages"])


@router.post("", response_model=dict, status_code=201)
async def create_package(
    data: PackageCreate,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    package_id = f"PKG-{uuid4().hex[:8].upper()}"
    document = package_document(
        package_id=package_id,
        name=data.name,
        package_type=data.package_type,
        price=data.price,
        duration_days=data.validity_days,
        download_speed=data.download_speed,
        upload_speed=data.upload_speed,
        mikrotik_profile=data.mikrotik_profile,
        max_devices=data.max_devices,
    )
    await db.packages.insert_one(document)
    document["_id"] = str(document["_id"])
    return success_response(message="Package created", data=document, status_code=201)


@router.get("", response_model=dict)
async def list_packages(
    package_type: str | None = None,
    active_only: bool = False,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    query = {}
    if package_type:
        query["package_type"] = package_type
    if active_only:
        query["is_active"] = True

    packages = []
    async for package in db.packages.find(query).sort("created_at", -1):
        package["_id"] = str(package["_id"])
        packages.append(package)

    return success_response(message="Packages retrieved", data=packages)


@router.get("/{package_id}", response_model=dict)
async def get_package(
    package_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    package = await db.packages.find_one({"package_id": package_id})
    if not package:
        raise NotFoundError("Package not found")
    package["_id"] = str(package["_id"])
    return success_response(message="Package retrieved", data=package)


@router.patch("/{package_id}", response_model=dict)
async def update_package(
    package_id: str,
    data: PackageUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise ValidationError("No fields supplied")

    result = await db.packages.update_one({"package_id": package_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise NotFoundError("Package not found")

    package = await db.packages.find_one({"package_id": package_id})
    package["_id"] = str(package["_id"])
    return success_response(message="Package updated", data=package)


@router.delete("/{package_id}", response_model=dict)
async def delete_package(
    package_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await db.packages.delete_one({"package_id": package_id})
    if result.deleted_count == 0:
        raise NotFoundError("Package not found")
    return success_response(message="Package deleted")
