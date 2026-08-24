from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_database
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import user_document
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
)
async def register_user(data: RegisterRequest):

    db = get_database()

    existing_user = await db.users.find_one(
        {"email": data.email.lower()}
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user_id = str(uuid4())

    document = user_document(
        user_id=user_id,
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
    )

    await db.users.insert_one(document)

    document.pop("_id", None)
    document.pop("password_hash", None)

    return document


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(data: LoginRequest):

    db = get_database()

    user = await db.users.find_one(
        {"email": data.email.lower()}
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.get("status") != "active":
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    token = create_access_token(
        user_id=user["user_id"],
        role=user["role"],
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=UserResponse,
)
async def current_user(
    user=Depends(get_current_user),
):
    return user