import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.database import Database, INDEXES


def test_purchase_transaction_voucher_index_is_required_for_settlement_safety():
    purchase_index = next(
        index
        for index in INDEXES["vouchers"]
        if index["keys"] == [("purchase_transaction_id", 1)]
    )
    assert purchase_index["unique"] is True
    assert purchase_index["sparse"] is True
    assert purchase_index["critical"] is True


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
