"""Application configuration using Pydantic Settings.
This module intentionally avoids hard-coded production secrets and enforces
strong environment variables when the app is running in production mode.
"""
from typing import List, Optional
import os

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Production-grade application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="DEVZEN CREATIONS", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URL")
    database_name: str = Field(default="isp_billing", alias="DATABASE_NAME")
    mongodb_max_pool_size: int = Field(default=50, alias="MONGODB_MAX_POOL_SIZE")
    mongodb_min_pool_size: int = Field(default=10, alias="MONGODB_MIN_POOL_SIZE")
    mongodb_max_idle_time_ms: int = Field(default=60000, alias="MONGODB_MAX_IDLE_TIME_MS")

    # JWT
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # RADIUS
    radius_secret: str = Field(default="", alias="RADIUS_SECRET")
    radius_api_secret: str = Field(default="", alias="RADIUS_API_SECRET")
    radius_host: str = Field(default="radius", alias="RADIUS_HOST")
    radius_auth_port: int = Field(default=1812, alias="RADIUS_AUTH_PORT")
    radius_acct_port: int = Field(default=1813, alias="RADIUS_ACCT_PORT")

    # M-Pesa
    mpesa_environment: str = Field(default="sandbox", alias="MPESA_ENVIRONMENT")

    # Automation
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    billing_grace_period_days: int = Field(default=3, alias="BILLING_GRACE_PERIOD_DAYS")

    # Notifications
    africas_talking_username: Optional[str] = Field(default=None, alias="AFRICAS_TALKING_USERNAME")
    africas_talking_api_key: Optional[str] = Field(default=None, alias="AFRICAS_TALKING_API_KEY")
    africas_talking_sender_id: Optional[str] = Field(default=None, alias="AFRICAS_TALKING_SENDER_ID")
    mpesa_consumer_key: Optional[str] = Field(default=None, alias="MPESA_CONSUMER_KEY")
    mpesa_consumer_secret: Optional[str] = Field(default=None, alias="MPESA_CONSUMER_SECRET")
    mpesa_shortcode: Optional[str] = Field(default=None, alias="MPESA_SHORTCODE")
    mpesa_passkey: Optional[str] = Field(default=None, alias="MPESA_PASSKEY")
    mpesa_callback_url: Optional[str] = Field(default=None, alias="MPESA_CALLBACK_URL")

    # Security
    cors_origins: List[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1", "test", "testserver"], alias="ALLOWED_HOSTS")
    rate_limit_per_minute: int = Field(default=100, alias="RATE_LIMIT_PER_MINUTE")
    router_encryption_key: str = Field(default="", alias="ROUTER_ENCRYPTION_KEY")
    timezone: str = Field(default="Africa/Nairobi", alias="TIMEZONE")
    currency: str = Field(default="KES", alias="CURRENCY")
    router_name: str = Field(default="nyaururu", alias="ROUTER_NAME")
    router_connection_mode: str = Field(default="direct", alias="ROUTER_CONNECTION_MODE")
    router_relay_url: Optional[str] = Field(default=None, alias="ROUTER_RELAY_URL")
    router_relay_token: Optional[str] = Field(default=None, alias="ROUTER_RELAY_TOKEN")
    router_host: str = Field(default="10.30.0.10", alias="ROUTER_HOST")
    router_port: int = Field(default=8728, alias="ROUTER_PORT")
    router_username: str = Field(default="isp-billing-api", alias="ROUTER_USERNAME")
    router_password: str = Field(default="", alias="ROUTER_PASSWORD")
    router_connection_timeout: int = Field(default=10, alias="ROUTER_CONNECTION_TIMEOUT")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            hosts = [host.strip() for host in v.split(",") if host.strip()]
        else:
            hosts = list(v)
        render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
        if render_hostname and render_hostname not in hosts:
            hosts.append(render_hostname)
        return hosts

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v_upper

    @field_validator("router_connection_mode")
    @classmethod
    def validate_router_connection_mode(cls, v):
        if v is None:
            return "direct"
        mode = str(v).strip().lower()
        allowed = {"direct", "vps_relay"}
        if mode not in allowed:
            raise ValueError("ROUTER_CONNECTION_MODE must be 'direct' or 'vps_relay'")
        return mode

    @field_validator("router_relay_url")
    @classmethod
    def validate_router_relay_url(cls, v):
        if not v:
            return v
        value = str(v).strip()
        if not value.startswith("https://"):
            raise ValueError("ROUTER_RELAY_URL must use HTTPS when relay mode is enabled")
        return value.rstrip("/")

    @field_validator("mongodb_url")
    @classmethod
    def validate_mongodb_url(cls, v):
        if not v.startswith("mongodb://") and not v.startswith("mongodb+srv://"):
            raise ValueError("MONGODB_URL must start with mongodb:// or mongodb+srv://")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self):
        env_name = (self.app_env or "development").lower()
        if env_name not in {"production", "prod"}:
            return self

        required = {
            "JWT_SECRET_KEY": self.jwt_secret_key,
            "RADIUS_SECRET": self.radius_secret,
            "RADIUS_API_SECRET": self.radius_api_secret,
            "ROUTER_ENCRYPTION_KEY": self.router_encryption_key,
        }

        missing = [name for name, value in required.items() if not value or len(value) < 32]
        if missing:
            raise ValueError(
                "Production mode requires strong non-empty values for: "
                + ", ".join(missing)
                + ". Configure them in your environment variables or .env file."
            )

        if self.router_connection_mode == "vps_relay":
            if not self.router_relay_url or not self.router_relay_token:
                raise ValueError(
                    "vps_relay mode requires ROUTER_RELAY_URL and ROUTER_RELAY_TOKEN environment variables."
                )

        return self


settings = Settings()
