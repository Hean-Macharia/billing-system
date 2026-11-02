import asyncio
from pprint import pprint
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def main():
    client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=30000,
        tz_aware=True,
    )

    try:
        await client.admin.command("ping")
        db = client[settings.database_name]

        router_id = ObjectId("6ab587aa145e0b7ff9adcf49")
        site_id = ObjectId("6aa1c1318c57af83b37a0e49")

        print("\n========== NAS CLIENTS ==========")
        async for doc in db.nas_clients.find({}, {"secret": 0}):
            pprint(doc)

        print("\n========== RB951 ROUTER ==========")
        pprint(await db.routers.find_one(
            {"_id": router_id},
            {"password": 0, "radius_secret": 0}
        ))

        print("\n========== NYAURURU SITE ==========")
        pprint(await db.sites.find_one({"_id": site_id}))

        print("\n========== ROUTERS LINKED TO NAS ==========")
        async for doc in db.routers.find(
            {"nas_client_id": {"$exists": True, "$ne": None}},
            {"password": 0, "radius_secret": 0}
        ):
            pprint(doc)

        print("\n========== NAS IP 10.30.0.10 ==========")
        pprint(await db.nas_clients.find_one(
            {"ip_address": "10.30.0.10"},
            {"secret": 0}
        ))

    finally:
        client.close()

asyncio.run(main())
