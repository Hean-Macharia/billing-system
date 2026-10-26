import pytest

from app.core.config import Settings


def test_vps_relay_mode_accepts_secure_config():
    cfg = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a" * 64,
        RADIUS_SECRET="b" * 64,
        RADIUS_API_SECRET="c" * 64,
        ROUTER_ENCRYPTION_KEY="d" * 64,
        ROUTER_CONNECTION_MODE="vps_relay",
        ROUTER_RELAY_URL="https://relay.example.com",
        ROUTER_RELAY_TOKEN="relay-token-value",
        ROUTER_HOST="10.30.0.10",
        ROUTER_PORT=8728,
        ROUTER_USERNAME="isp-billing-api",
    )

    assert cfg.router_connection_mode == "vps_relay"
    assert cfg.router_username == "isp-billing-api"
    assert cfg.router_relay_url == "https://relay.example.com"
    assert cfg.router_relay_token == "relay-token-value"


def test_vps_relay_requires_valid_url_and_token():
    with pytest.raises(ValueError):
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a" * 64,
            RADIUS_SECRET="b" * 64,
            RADIUS_API_SECRET="c" * 64,
            ROUTER_ENCRYPTION_KEY="d" * 64,
            ROUTER_CONNECTION_MODE="vps_relay",
            ROUTER_RELAY_URL="not-a-url",
            ROUTER_RELAY_TOKEN="",
        )
