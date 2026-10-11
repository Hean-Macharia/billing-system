import socket

import pytest


def _mongodb_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 27017), timeout=1):
            return True
    except OSError:
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_db: mark tests that require a running MongoDB service",
    )


def pytest_collection_modifyitems(config, items):
    if _mongodb_available():
        return

    skip_db = pytest.mark.skip(reason="MongoDB server not available in this environment")
    for item in items:
        if "requires_db" in item.keywords:
            item.add_marker(skip_db)
