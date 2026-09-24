import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def fix():
    client = AsyncIOMotorClient('mongodb+srv://courseschecker_db_user:KBH7w8Ik5xvILPz6@cluster0.k8lk88k.mongodb.net/')
    db = client['isp_billing']
    
    print('Dropping stale code_1 index...')
    await db.vouchers.drop_index('code_1')
    print('Done. Verifying indexes:')
    
    indexes = await db.vouchers.index_information()
    for name, info in indexes.items():
        print(f'  {name}: unique={info.get("unique", False)}, key={info.get("key")}')
    
    client.close()

asyncio.run(fix())
