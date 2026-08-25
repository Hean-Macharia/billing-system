"""Authentication API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user, get_db, require_permission, require_role
from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB, UserRole
from app.schemas.auth import (
    PasswordChange,
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import AuthService
from app.utils.helpers import error_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _to_user_response(user: UserInDB) -> UserResponse:
    """Convert UserInDB to public UserResponse."""
    return UserResponse(
        _id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        phone=user.phone,
        avatar_url=user.avatar_url,
        permissions=user.permissions,
        is_email_verified=user.is_email_verified,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    data: UserRegister,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[UserInDB] = Depends(get_current_user),
):
    """Register a new user.

    - Anyone can register as CUSTOMER
    - Only SUPER_ADMIN/ADMIN can assign other roles
    """
    auth_service = AuthService(db)

    # If no auth, force CUSTOMER role
    if current_user is None:
        if data.role != UserRole.CUSTOMER:
            raise AuthenticationError("Unauthorized role assignment. Register as customer or login as admin.")
        created_by = None
    else:
        # Only admins can create non-customer accounts
        if data.role != UserRole.CUSTOMER and current_user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
            raise AuthenticationError("Only administrators can create staff accounts")
        created_by = str(current_user.id)

    user = await auth_service.register(data, created_by=created_by)
    return success_response(
        message="User registered successfully",
        data=_to_user_response(user),
        status_code=status.HTTP_201_CREATED,
    )


@router.post("/login", response_model=dict)
async def login(
    request: Request,
    data: UserLogin,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Authenticate user and return JWT tokens."""
    auth_service = AuthService(db)
    user = await auth_service.authenticate(data.email, data.password)
    tokens = await auth_service.create_tokens(user)
    return success_response(
        message="Login successful",
        data={
            "user": _to_user_response(user),
            "tokens": tokens.model_dump(),
        },
    )


@router.post("/refresh", response_model=dict)
async def refresh(
    request: Request,
    body: RefreshTokenRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Refresh access token using a refresh token."""
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_access_token(body.refresh_token)
    return success_response(
        message="Token refreshed successfully",
        data=tokens.model_dump(),
    )


@router.post("/logout", response_model=dict)
async def logout(
    request: Request,
    refresh_token: Optional[str] = Header(None, alias="x-refresh-token"),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Logout current user. Optionally revoke a specific refresh token."""
    auth_service = AuthService(db)
    await auth_service.logout(str(current_user.id), refresh_token)
    return success_response(message="Logout successful")


@router.get("/me", response_model=dict)
async def get_me(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    """Get current authenticated user profile."""
    return success_response(
        message="User profile retrieved",
        data=_to_user_response(current_user),
    )


@router.patch("/me", response_model=dict)
async def update_me(
    request: Request,
    data: UserUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update current user profile."""
    from datetime import datetime, timezone
    from bson import ObjectId

    update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise ValidationError("No fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data},
    )

    # Fetch updated user
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(str(current_user.id))
    return success_response(
        message="Profile updated successfully",
        data=_to_user_response(user),
    )


@router.post("/change-password", response_model=dict)
async def change_password(
    request: Request,
    data: PasswordChange,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Change current user password."""
    auth_service = AuthService(db)
    await auth_service.change_password(
        str(current_user.id),
        data.current_password,
        data.new_password,
    )
    return success_response(message="Password changed successfully. Please login again.")


# ─────────────────────────────────────────────────────────────
# Admin-only user management endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/users", response_model=dict)
async def list_users(
    request: Request,
    role: Optional[UserRole] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.USERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all users (admin only)."""
    query = {}
    if role:
        query["role"] = role.value
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"username": {"$regex": search, "$options": "i"}},
            {"full_name": {"$regex": search, "$options": "i"}},
        ]

    skip = (page - 1) * limit
    total = await db.users.count_documents(query)
    cursor = db.users.find(query).skip(skip).limit(limit).sort("created_at", -1)

    users = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        users.append(_to_user_response(UserInDB(**doc)))

    from app.utils.helpers import paginated_response
    return paginated_response(
        data=users,
        total=total,
        page=page,
        limit=limit,
        message="Users retrieved successfully",
    )


@router.get("/users/{user_id}", response_model=dict)
async def get_user(
    request: Request,
    user_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.USERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific user by ID (admin only)."""
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)
    return success_response(
        message="User retrieved successfully",
        data=_to_user_response(user),
    )


@router.patch("/users/{user_id}/status", response_model=dict)
async def update_user_status(
    request: Request,
    user_id: str,
    status: str,
    current_user: UserInDB = Depends(require_role(UserRole.ADMIN)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update user status (admin only)."""
    from datetime import datetime, timezone
    from bson import ObjectId

    valid_statuses = ["active", "inactive", "suspended", "pending"]
    if status not in valid_statuses:
        raise ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")

    result = await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("User not found")

    return success_response(message=f"User status updated to {status}")