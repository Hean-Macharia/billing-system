"""Authentication business logic."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_refresh_token_expiry_seconds,
    get_token_expiry_seconds,
    hash_password,
    verify_password,
)
from app.models.user import UserInDB, UserRole, UserStatus, get_permissions_for_role
from app.schemas.auth import TokenResponse, UserRegister

logger = get_logger(__name__)


class AuthService:
    """Service layer for authentication operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.users

    async def register(self, data: UserRegister, created_by: Optional[str] = None) -> UserInDB:
        """Register a new user. Only SUPER_ADMIN/ADMIN can create non-customer roles."""
        existing = await self.collection.find_one({"email": data.email})
        if existing:
            raise ConflictError("User with this email already exists")

        existing = await self.collection.find_one({"username": data.username})
        if existing:
            raise ConflictError("Username already taken")

        hashed_pw = hash_password(data.password)
        permissions = get_permissions_for_role(data.role)

        user_doc = {
            "email": data.email,
            "username": data.username,
            "full_name": data.full_name,
            "hashed_password": hashed_pw,
            "role": data.role.value,
            "status": UserStatus.ACTIVE.value,
            "phone": data.phone,
            "permissions": permissions,
            "is_email_verified": False,
            "failed_login_attempts": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "created_by": created_by,
            "refresh_tokens": [],
        }

        result = await self.collection.insert_one(user_doc)
        user_doc["_id"] = str(result.inserted_id)
        logger.info(f"User registered: {data.email} ({data.role.value})")
        return UserInDB(**user_doc)

    async def authenticate(self, email: str, password: str) -> UserInDB:
        """Authenticate user by email and password."""
        doc = await self.collection.find_one({"email": email})
        if not doc:
            raise AuthenticationError("Invalid email or password")

        # Convert ObjectId to string before Pydantic validation
        doc["_id"] = str(doc["_id"])
        user = UserInDB(**doc)

        if user.status == UserStatus.SUSPENDED:
            raise AuthenticationError("Account is suspended. Contact administrator.")
        if user.status == UserStatus.INACTIVE:
            raise AuthenticationError("Account is inactive.")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AuthenticationError(f"Account locked until {user.locked_until.isoformat()}")

        if not verify_password(password, user.hashed_password):
            await self._record_failed_attempt(str(user.id))
            raise AuthenticationError("Invalid email or password")

        if user.failed_login_attempts > 0:
            await self.collection.update_one(
                {"_id": ObjectId(user.id)},
                {"$set": {"failed_login_attempts": 0, "locked_until": None}},
            )

        await self.collection.update_one(
            {"_id": ObjectId(user.id)},
            {"$set": {"last_login": datetime.now(timezone.utc)}},
        )

        return user

    async def _record_failed_attempt(self, user_id: str) -> None:
        """Increment failed login attempts and lock if threshold reached."""
        max_attempts = 5
        lockout_minutes = 30

        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$inc": {"failed_login_attempts": 1}},
        )

        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if doc and doc.get("failed_login_attempts", 0) >= max_attempts:
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
            await self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"locked_until": locked_until}},
            )
            logger.warning(f"Account locked: {user_id} until {locked_until.isoformat()}")

    async def create_tokens(self, user: UserInDB) -> TokenResponse:
        """Create access and refresh tokens for a user."""
        user_id = str(user.id)
        permissions = user.permissions or get_permissions_for_role(user.role)

        access_token = create_access_token(
            user_id=user_id,
            email=user.email,
            role=user.role.value,
            permissions=permissions,
        )
        refresh_token = create_refresh_token(user_id=user_id)

        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$push": {"refresh_tokens": refresh_token}},
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=get_token_expiry_seconds(),
            refresh_expires_in=get_refresh_token_expiry_seconds(),
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using a valid refresh token."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AuthenticationError("Invalid or expired refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid refresh token payload")

        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not doc:
            raise NotFoundError("User not found")

        doc["_id"] = str(doc["_id"])
        user = UserInDB(**doc)

        if refresh_token not in (user.refresh_tokens or []):
            raise AuthenticationError("Refresh token has been revoked")

        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"refresh_tokens": refresh_token}},
        )

        return await self.create_tokens(user)

    async def logout(self, user_id: str, refresh_token: Optional[str] = None) -> None:
        """Logout user."""
        if refresh_token:
            await self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"refresh_tokens": refresh_token}},
            )
            logger.info(f"User {user_id} logged out (single session)")
        else:
            await self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"refresh_tokens": []}},
            )
            logger.info(f"User {user_id} logged out (all sessions)")

    async def get_user_by_id(self, user_id: str) -> UserInDB:
        """Get user by ID."""
        from bson.errors import InvalidId
        try:
            doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        except InvalidId:
            raise NotFoundError("Invalid user ID format")
        if not doc:
            raise NotFoundError("User not found")
        doc["_id"] = str(doc["_id"])
        return UserInDB(**doc)

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        """Change user password."""
        user = await self.get_user_by_id(user_id)
        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")

        new_hash = hash_password(new_password)
        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "hashed_password": new_hash,
                    "password_changed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"refresh_tokens": []}},
        )
        logger.info(f"Password changed for user {user_id}")