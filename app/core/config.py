"""Application configuration using Pydantic Settings.
Matches the user's .env file exactly: MONGODB_URL, JWT_SECRET_KEY, APP_VERSION, MPESA_*.
"""
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Production-grade application settings."""

    # Application
    app_name: str = Field(default="ISP Billing System", alias="APP_NAME")
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
    jwt_secret_key: str = Field(
        default="dev-jwt-secret-change-in-production-min-32-chars-long",
        alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # RADIUS
    radius_secret: str = Field(default="dev-radius-secret-change-me", alias="RADIUS_SECRET")
    radius_host: str = Field(default="radius", alias="RADIUS_HOST")
    radius_auth_port: int = Field(default=1812, alias="RADIUS_AUTH_PORT")
    radius_acct_port: int = Field(default=1813, alias="RADIUS_ACCT_PORT")

    # M-Pesa (Phase 5)
    mpesa_environment: str = Field(default="sandbox", alias="MPESA_ENVIRONMENT")
    mpesa_consumer_key: Optional[str] = Field(default=None, alias="MPESA_CONSUMER_KEY")
    mpesa_consumer_secret: Optional[str] = Field(default=None, alias="MPESA_CONSUMER_SECRET")
    mpesa_shortcode: Optional[str] = Field(default=None, alias="MPESA_SHORTCODE")
    mpesa_passkey: Optional[str] = Field(default=None, alias="MPESA_PASSKEY")
    mpesa_callback_url: Optional[str] = Field(default=None, alias="MPESA_CALLBACK_URL")

    # Security
    cors_origins: List[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1"], alias="ALLOWED_HOSTS")
    rate_limit_per_minute: int = Field(default=100, alias="RATE_LIMIT_PER_MINUTE")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v_upper

    @field_validator("mongodb_url")
    @classmethod
    def validate_mongodb_url(cls, v):
        if not v.startswith("mongodb://") and not v.startswith("mongodb+srv://"):
            raise ValueError("MONGODB_URL must start with mongodb:// or mongodb+srv://")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
