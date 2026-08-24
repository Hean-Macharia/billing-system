"""
Security utilities - Phase 1: structure only.
Phase 2 will add: password hashing, JWT creation/verification, role checks.
"""
from fastapi import Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> Optional[dict]:
    """Placeholder for Phase 2 JWT authentication."""
    return None

async def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = None) -> dict:
    from app.core.exceptions import AuthenticationError
    raise AuthenticationError(
        message="Authentication required. Please login.",
        details={"header": "Authorization", "scheme": "Bearer"}
    )