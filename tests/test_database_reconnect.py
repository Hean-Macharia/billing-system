import asyncio

import pytest

from app.core.database import database


@pytest.mark.asyncio
async def test_database_connect_reconnects_closed_loop(monkeypatch):
    await database.connect()

    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    monkeypatch.setattr(database.client, "get_io_loop", lambda: closed_loop)

    await database.connect()

    assert database.client is not None
    assert database.db is not None
    await database.disconnect()
