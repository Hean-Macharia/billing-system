import logging

from fastapi.testclient import TestClient

from app.core.dependencies import get_db
from app.main import app
from app.routes.radius_auth import verify_radius_secret


def test_radius_auth_validation_error_redacts_submitted_values(caplog, monkeypatch):
    sensitive_value = "voucher-and-password-must-not-leak"

    async def unused_database_dependency():
        return None

    monkeypatch.setitem(app.dependency_overrides, get_db, unused_database_dependency)
    monkeypatch.setitem(app.dependency_overrides, verify_radius_secret, lambda: True)
    caplog.set_level(logging.WARNING, logger="app.main")

    response = TestClient(app).post(
        "/api/v1/radius/auth",
        json={"User-Password": {"sensitive_marker": sensitive_value}},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {"loc": ["body", "User-Password"], "type": "string_type"},
        ],
    }
    assert sensitive_value not in response.text
    assert sensitive_value not in caplog.text
    assert "/api/v1/radius/auth" in caplog.text
    assert "User-Password" in caplog.text
    assert "string_type" in caplog.text
