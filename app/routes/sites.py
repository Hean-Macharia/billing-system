"""Site (tower/POP location) CRUD.

Was previously a bare, unauthenticated POST-only stub accepting an
arbitrary raw dict, never returning a usable id (pymongo mutates the dict
with a raw ObjectId in place, which FastAPI can't JSON-serialize - a 500
on every call), and had no list/get/update/delete at all despite routers,
voucher batches, and hotspot plans all referencing site_id. Rebuilt to
match the rest of the app's conventions.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.user import Permission, UserInDB
from app.schemas.site import SiteCreate, SiteUpdate
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/sites", tags=["Sites"])


def _to_response(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("", response_model=dict, status_code=201)
async def create_site(
    data: SiteCreate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    existing = await db.sites.find_one({"code": data.code})
    if existing:
        raise ConflictError(f"A site with code '{data.code}' already exists")

    now = datetime.now(timezone.utc)
    doc = data.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now
    result = await db.sites.insert_one(doc)
    doc["_id"] = result.inserted_id
    return success_response(message="Site created", data=_to_response(doc), status_code=201)


@router.get("", response_model=dict)
async def list_sites(
    status_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    total = await db.sites.count_documents(query)
    cursor = db.sites.find(query).skip(skip).limit(limit).sort("name", 1)
    sites = [_to_response(doc) async for doc in cursor]
    return paginated_response(data=sites, total=total, page=page, limit=limit)


@router.get("/{site_id}", response_model=dict)
async def get_site(
    site_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc
    doc = await db.sites.find_one({"_id": oid})
    if not doc:
        raise NotFoundError("Site not found")
    return success_response(message="Site retrieved", data=_to_response(doc))


@router.patch("/{site_id}", response_model=dict)
async def update_site(
    site_id: str,
    data: SiteUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise ValidationError("No fields to update")
    update_data["updated_at"] = datetime.now(timezone.utc)

    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc

    result = await db.sites.update_one({"_id": oid}, {"$set": update_data})
    if result.matched_count == 0:
        raise NotFoundError("Site not found")
    doc = await db.sites.find_one({"_id": oid})
    return success_response(message="Site updated", data=_to_response(doc))


@router.delete("/{site_id}", response_model=dict)
async def delete_site(
    site_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc
    result = await db.sites.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise NotFoundError("Site not found")
    return success_response(message="Site deleted")
"""Site (tower/POP location) CRUD.

Was previously a bare, unauthenticated POST-only stub accepting an
arbitrary raw dict, never returning a usable id (pymongo mutates the dict
with a raw ObjectId in place, which FastAPI can't JSON-serialize - a 500
on every call), and had no list/get/update/delete at all despite routers,
voucher batches, and hotspot plans all referencing site_id. Rebuilt to
match the rest of the app's conventions.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.user import Permission, UserInDB
from app.schemas.site import SiteCreate, SiteUpdate
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/sites", tags=["Sites"])


def _to_response(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("", response_model=dict, status_code=201)
async def create_site(
    data: SiteCreate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    existing = await db.sites.find_one({"code": data.code})
    if existing:
        raise ConflictError(f"A site with code '{data.code}' already exists")

    now = datetime.now(timezone.utc)
    doc = data.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now
    result = await db.sites.insert_one(doc)
    doc["_id"] = result.inserted_id
    return success_response(message="Site created", data=_to_response(doc), status_code=201)


@router.get("", response_model=dict)
async def list_sites(
    status_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    total = await db.sites.count_documents(query)
    cursor = db.sites.find(query).skip(skip).limit(limit).sort("name", 1)
    sites = [_to_response(doc) async for doc in cursor]
    return paginated_response(data=sites, total=total, page=page, limit=limit)


@router.get("/{site_id}", response_model=dict)
async def get_site(
    site_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc
    doc = await db.sites.find_one({"_id": oid})
    if not doc:
        raise NotFoundError("Site not found")
    return success_response(message="Site retrieved", data=_to_response(doc))


@router.patch("/{site_id}", response_model=dict)
async def update_site(
    site_id: str,
    data: SiteUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise ValidationError("No fields to update")
    update_data["updated_at"] = datetime.now(timezone.utc)

    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc

    result = await db.sites.update_one({"_id": oid}, {"$set": update_data})
    if result.matched_count == 0:
        raise NotFoundError("Site not found")
    doc = await db.sites.find_one({"_id": oid})
    return success_response(message="Site updated", data=_to_response(doc))


@router.delete("/{site_id}", response_model=dict)
async def delete_site(
    site_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(site_id)
    except Exception as exc:
        raise NotFoundError("Site not found") from exc
    result = await db.sites.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise NotFoundError("Site not found")
    return success_response(message="Site deleted")
