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

    # Compound accounting indexes are deliberately managed by the explicit
    # preflighted migration, never created as a startup side effect.
    for collection_name, definitions in INDEXES.items():
        for index in definitions:
            if index.get("manual_migration"):
                await database.db[collection_name].create_index(index["keys"], unique=True)

    await database._create_indexes()
    await database._create_indexes()

    assert {
        collection: [tuple(index["keys"]) for index in indexes]
        for collection, indexes in INDEXES.items()
    } == original_keys
    assert "email_1" in await database.db.users.index_information()
    client.close()


@pytest.mark.asyncio
async def test_missing_manual_radius_indexes_fail_before_automatic_index_creation():
    client = AsyncMongoMockClient(tz_aware=True)
    database = Database()
    database.db = client["manual_radius_indexes_test"]

    with pytest.raises(RuntimeError, match="manually migrated unique index"):
        await database._create_indexes()

    # Startup must stop before creating any indexes in other collections.
    assert "email_1" not in await database.db.users.index_information()
    assert "acct_session_id_1_nas_ip_address_1" not in await database.db.radius_sessions.index_information()
    client.close()
