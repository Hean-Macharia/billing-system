from fastapi import APIRouter


router = APIRouter(
    prefix="/api/v1/routers",
    tags=["Routers"],
)


@router.get("/health")
async def router_health():
    return {
        "status": "ok",
        "service": "router-management",
    }