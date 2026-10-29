import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.database import Database, INDEXES


@pytest.mark.asyncio
async def test_index_creation_is_repeatable_without_mutating_definitions():
    client = AsyncMongoMockClient(tz_aware=True)
    database = Database()
    database.db = client["database_index_test"]
    original_keys = {
        collection: [tuple(index["keys"]) for index in indexes]
        for collection, indexes in INDEXES.items()
    }

    await database._create_indexes()
    await database._create_indexes()

    assert {
        collection: [tuple(index["keys"]) for index in indexes]
        for collection, indexes in INDEXES.items()
    } == original_keys
    assert "email_1" in await database.db.users.index_information()
    client.close()
