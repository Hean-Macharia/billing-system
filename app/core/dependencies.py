"""FastAPI dependencies for the application."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import database
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.core.security import decode_token
from app.models.user import Permission, UserInDB, UserRole, UserStatus, has_permission

logger = get_logger(__name__)
security_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIOMotorDatabase:
    """Yield the MongoDB database instance."""
    return database.db


class PaginationParams:
    """Pagination dependency."""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        limit: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.limit = limit
        self.skip = (page - 1) * limit


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> Optional[UserInDB]:
    """Extract and validate the current user from JWT token.

    Returns None if no token provided (for optional auth endpoints like public registration).
    Raises AuthenticationError if token is invalid.
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise AuthenticationError("Invalid or expired token")

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type. Use access token.")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    # Fetch user from DB
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        raise AuthenticationError("Invalid user ID in token")

    if not doc:
        raise AuthenticationError("User not found")

    doc["_id"] = str(doc["_id"])
    user = UserInDB(**doc)

    # FIX: Use UserStatus not UserRole
    if user.status == UserStatus.SUSPENDED:
        raise AuthenticationError("Account is suspended")
    if user.status == UserStatus.INACTIVE:
        raise AuthenticationError("Account is inactive")

    # Attach user to request state for middleware/logging
    request.state.user = user
    return user


async def require_auth(
    current_user: Optional[UserInDB] = Depends(get_current_user),
) -> UserInDB:
    """Require authenticated user. Raises if not authenticated."""
    if current_user is None:
        raise AuthenticationError("Authentication required")
    return current_user


def require_role(required_role: UserRole):
    """Dependency factory to require a specific role or higher (admin hierarchy)."""
    async def _check_role(
        current_user: UserInDB = Depends(require_auth),
    ) -> UserInDB:
        # Role hierarchy: super_admin > admin > others
        role_hierarchy = {
            UserRole.SUPER_ADMIN: 3,
            UserRole.ADMIN: 2,
        }
        user_level = role_hierarchy.get(current_user.role, 1)
        required_level = role_hierarchy.get(required_role, 1)

        # If exact match required (non-admin roles), check exact
        if required_role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
            if current_user.role != required_role:
                raise AuthorizationError(f"Role '{required_role.value}' required")
        else:
            # For admin endpoints, super_admin can access admin endpoints
            if user_level < required_level:
                raise AuthorizationError(f"Role '{required_role.value}' or higher required")

        return current_user
    return _check_role


def require_permission(required_permission: str):
    """Dependency factory to require a specific permission."""
    async def _check_permission(
        current_user: UserInDB = Depends(require_auth),
    ) -> UserInDB:
        # SUPER_ADMIN bypasses all permission checks
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user

        # Check explicit permissions
        user_permissions = current_user.permissions or []
        if required_permission not in user_permissions:
            raise AuthorizationError(f"Permission '{required_permission}' required")
        return current_user
    return _check_permission


async def verify_cors_origin(request: Request) -> bool:
    """Verify the request origin against allowed CORS origins."""
    origin = request.headers.get("origin", "")
    allowed = settings.cors_origins
    if "*" in allowed or not origin:
        return True
    return origin in allowed