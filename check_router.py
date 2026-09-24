import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings

ROUTER_ID = "6aa54a752e0ba89e0c4bc5fb"

async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    r = await db.routers.find_one({"_id": ObjectId(ROUTER_ID)})
    if not r:
        print("Router NOT FOUND in database")
    else:
        for k in ["name", "api_type", "ip_address", "port", "use_ssl", "username"]:
            print(f"{k}: {r.get(k)!r}")
    client.close()

asyncio.run(main())
