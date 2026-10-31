import asyncio
import importlib

import pytest

from app.core.database import database
from app.core.config import settings


@pytest.mark.asyncio
async def test_database_connect_reconnects_closed_loop(monkeypatch):
    database_module = importlib.import_module("app.core.database")
    monkeypatch.setattr(settings, "mongodb_url", "mongodb://127.0.0.1:27017/reconnect_test")
    monkeypatch.setattr(settings, "database_name", "reconnect_test")

    def unavailable_database_client(*_args, **_kwargs):
        raise RuntimeError("Use the in-memory test database")

    monkeypatch.setattr(database_module, "AsyncIOMotorClient", unavailable_database_client)
    await database.connect()

    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    monkeypatch.setattr(database.client, "get_io_loop", lambda: closed_loop)

    await database.connect()

    assert database.client is not None
    assert database.db is not None
    await database.disconnect()
