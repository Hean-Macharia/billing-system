from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_database
from app.core.security import get_current_user
from app.models.package import package_document
from app.schemas.package import (
    PackageCreate,
    PackageUpdate,
)


router = APIRouter(
    prefix="/api/v1/packages",
    tags=["Packages"],
)


@router.post("/")
async def create_package(
    data: PackageCreate,
    current_user=Depends(get_current_user),
):

    db = get_database()

    package_id = f"PKG-{uuid4().hex[:8].upper()}"

    document = package_document(
        package_id=package_id,
        name=data.name,
        package_type=data.package_type,
        download_speed=data.download_speed,
        upload_speed=data.upload_speed,
        price=data.price,
        validity_days=data.validity_days,
    )

    document["mikrotik_profile"] = data.mikrotik_profile
    document["max_devices"] = data.max_devices

    await db.packages.insert_one(document)

    document.pop("_id", None)

    return document


@router.get("/")
async def get_packages(
    current_user=Depends(get_current_user),
):

    db = get_database()

    packages = []

    cursor = db.packages.find({})

    async for package in cursor:
        package.pop("_id", None)
        packages.append(package)

    return {
        "count": len(packages),
        "packages": packages,
    }


@router.get("/{package_id}")
async def get_package(
    package_id: str,
    current_user=Depends(get_current_user),
):

    db = get_database()

    package = await db.packages.find_one(
        {"package_id": package_id}
    )

    if not package:
        raise HTTPException(
            status_code=404,
            detail="Package not found",
        )

    package.pop("_id", None)

    return package


@router.patch("/{package_id}")
async def update_package(
    package_id: str,
    data: PackageUpdate,
    current_user=Depends(get_current_user),
):

    db = get_database()

    update_data = data.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields supplied",
        )

    result = await db.packages.update_one(
        {"package_id": package_id},
        {"$set": update_data},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Package not found",
        )

    package = await db.packages.find_one(
        {"package_id": package_id}
    )

    package.pop("_id", None)

    return package