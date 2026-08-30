from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_db

router = APIRouter(prefix="/api/v1/sites", tags=["Sites"])

@router.post("", response_model=dict)
async def create_site(
    site: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Register a new site (e.g. tower location).
    """
    # Example: insert into MongoDB
    result = await db["sites"].insert_one(site)
    if not result.inserted_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create site")
    return {"success": True, "message": "Site created", "data": site}
