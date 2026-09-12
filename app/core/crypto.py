"""Symmetric encryption helpers for credentials stored at rest (router
passwords, RADIUS shared secrets, etc).

Uses Fernet (AES-128-CBC + HMAC). If ROUTER_ENCRYPTION_KEY is not set in
the environment, a key is deterministically derived from JWT_SECRET_KEY so
local/dev environments work out of the box. Set ROUTER_ENCRYPTION_KEY
explicitly in production so credentials survive a JWT secret rotation.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _derive_key() -> bytes:
    raw = settings.router_encryption_key
    if raw:
        candidate = raw.encode()
        try:
            # Already a valid urlsafe-base64 32-byte Fernet key
            Fernet(candidate)
            return candidate
        except (ValueError, Exception):
            pass
        # Treat as an arbitrary passphrase and derive a 32-byte key from it
        digest = hashlib.sha256(candidate).digest()
        return base64.urlsafe_b64encode(digest)

    # Dev fallback - deterministic, but should not be relied on in production
    digest = hashlib.sha256(f"router-encryption::{settings.jwt_secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())


def encrypt_value(value: str) -> str:
    """Encrypt a plaintext string for storage."""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(token: str) -> str:
    """Decrypt a value previously produced by encrypt_value()."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Failed to decrypt stored credential - ROUTER_ENCRYPTION_KEY may have changed"
        ) from exc
