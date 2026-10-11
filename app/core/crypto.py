"""Symmetric encryption helpers for credentials stored at rest (router
passwords, RADIUS shared secrets, etc).

Uses Fernet (AES-128-CBC + HMAC). In local development, generate a per-process
key when one is not configured so we don't ship any hardcoded secret defaults.
Set ROUTER_ENCRYPTION_KEY explicitly in production so credentials survive a JWT
secret rotation.
"""
import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _derive_key() -> bytes:
    raw = (settings.router_encryption_key or "").strip()
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

    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("ROUTER_ENCRYPTION_KEY is required in production")

    generated = secrets.token_urlsafe(32)
    settings.router_encryption_key = generated
    digest = hashlib.sha256(generated.encode()).digest()
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
