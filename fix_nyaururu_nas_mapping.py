import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

SITE_ID = "6aa1c1318c57af83b37a0e49"
ROUTER_ID = "6ab587aa145e0b7ff9adcf49"
NAS_IP = "10.30.0.10"

async def main():
    client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=30000,
        tz_aware=True,
    )

    try:
        await client.admin.command("ping")
        db = client[settings.database_name]

        site_oid = ObjectId(SITE_ID)
        router_oid = ObjectId(ROUTER_ID)

        print("Connected database:", settings.database_name)

        # Verify the existing site.
        site = await db.sites.find_one({
            "_id": site_oid,
            "status": "active"
        })

        if not site:
            raise RuntimeError("STOP: Active Nyaururu site not found.")

        # Verify the intended router.
        router = await db.routers.find_one({
            "_id": router_oid,
            "site_id": SITE_ID,
            "status": "online"
        })

        if not router:
            raise RuntimeError("STOP: Expected online RB951 router not found.")

        if router.get("nas_client_id"):
            raise RuntimeError(
                "STOP: Router already has a NAS mapping. "
                "No changes made."
            )

        # Refuse to create a duplicate NAS.
        existing = await db.nas_clients.find_one({
            "ip_address": NAS_IP
        })

        if existing:
            raise RuntimeError(
                "STOP: NAS IP already exists. No changes made."
            )

        # Require the unique IP index before writing.
        indexes = await db.nas_clients.index_information()
        unique_ip_index = any(
            index.get("unique") is True
            and index.get("key") == [("ip_address", 1)]
            for index in indexes.values()
        )

        if not unique_ip_index:
            raise RuntimeError(
                "STOP: Unique NAS IP index is missing. No changes made."
            )

        now = datetime.now(timezone.utc)

        nas_document = {
            "name": "MikroTik-Nyaururu-RB951",
            "site_id": SITE_ID,
            "ip_address": NAS_IP,
            "nas_identifier": None,
            "secret": "NOT_USED_BY_RADIUS",
            "description": (
                "NAS identity mapping for RB951. "
                "Placeholder field only; actual RADIUS shared secret "
                "is configured separately in FreeRADIUS and MikroTik."
            ),
            "location": "Nyaururu",
            "nas_type": "mikrotik",
            "coa_port": 3799,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

        # Perform both writes in one MongoDB transaction.
        async with await client.start_session() as session:
            async with session.start_transaction():
                result = await db.nas_clients.insert_one(
                    nas_document,
                    session=session
                )

                nas_id = str(result.inserted_id)

                update = await db.routers.update_one(
                    {
                        "_id": router_oid,
                        "site_id": SITE_ID,
                        "status": "online",
                        "nas_client_id": None,
                    },
                    {
                        "$set": {
                            "nas_client_id": nas_id,
                            "updated_at": now,
                        }
                    },
                    session=session,
                )

                if update.modified_count != 1:
                    raise RuntimeError(
                        "Router mapping update failed. "
                        "Transaction will be aborted."
                    )

        print("\n========== MAPPING CREATED ==========")
        print("NAS ID:", nas_id)
        print("NAS IP:", NAS_IP)
        print("NAS site:", SITE_ID)
        print("Router ID:", ROUTER_ID)
        print("Router NAS reference:", nas_id)

        print("\n========== VERIFICATION ==========")

        verified_nas = await db.nas_clients.find_one({
            "_id": ObjectId(nas_id)
        }, {"secret": 0})

        verified_router = await db.routers.find_one({
            "_id": router_oid
        }, {"password": 0, "radius_secret": 0})

        print("NAS record:", verified_nas)
        print("Router NAS mapping:", verified_router.get("nas_client_id"))
        print("Router site:", verified_router.get("site_id"))

        if verified_router.get("nas_client_id") != nas_id:
            raise RuntimeError("VERIFICATION FAILED.")

        print("\nSUCCESS: NAS identity mapping is established.")

    finally:
        client.close()

asyncio.run(main())
