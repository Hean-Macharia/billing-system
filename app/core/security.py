"""Security utilities: password hashing and JWT tokens."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings


def _get_jwt_secret() -> str:
    """Return the active JWT secret.

    In local development, create a per-process secret instead of shipping a
    hardcoded default that can be reused across environments.
    """
    secret = (settings.jwt_secret_key or "").strip()
    if secret:
        return secret
    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("JWT_SECRET_KEY is required in production")
    generated = secrets.token_urlsafe(32)
    settings.jwt_secret_key = generated
    return generated


def _get_algorithm() -> str:
    return settings.jwt_algorithm or "HS256"


# Password hashing
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hash."""
    plain_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hash_bytes)


def hash_password(password: str) -> str:
    """Hash a plain password using bcrypt."""
    password_bytes = password.encode("utf-8")[:72]  # bcrypt limit
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    permissions: List[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    secret_key = _get_jwt_secret()
    algorithm = _get_algorithm()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "permissions": permissions,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    secret_key = _get_jwt_secret()
    algorithm = _get_algorithm()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.refresh_token_expire_days)
    )
    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=[_get_algorithm()])
    except JWTError:
        return None


def get_token_expiry_seconds() -> int:
    """Return access token expiry in seconds."""
    return settings.access_token_expire_minutes * 60


def get_refresh_token_expiry_seconds() -> int:
    """Return refresh token expiry in seconds."""
    return settings.refresh_token_expire_days * 24 * 60 * 60


# ── FastAPI dependency for current user ──
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency to extract and validate the current user from JWT."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "permissions": payload.get("permissions", []),
    }
