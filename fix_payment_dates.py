import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]

    # Fix payment_date=None
    count = await db.payments.count_documents({"payment_date": None})
    print(f"Payments with payment_date=None: {count}")
    if count > 0:
        result = await db.payments.update_many(
            {"payment_date": None},
            {"$set": {"payment_date": datetime.now(timezone.utc)}},
        )
        print(f"  -> Fixed {result.modified_count}")

    # Fix payment_date field missing entirely
    missing = await db.payments.count_documents({"payment_date": {"$exists": False}})
    print(f"Payments missing payment_date field: {missing}")
    if missing > 0:
        result = await db.payments.update_many(
            {"payment_date": {"$exists": False}},
            {"$set": {"payment_date": datetime.now(timezone.utc)}},
        )
        print(f"  -> Fixed {result.modified_count}")

    client.close()
    print("Done.")

asyncio.run(main())
