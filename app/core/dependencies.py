"""
FastAPI dependencies.
"""
from fastapi import Request
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import database
from app.core.logging import get_logger

logger = get_logger(__name__)

async def get_db() -> AsyncIOMotorDatabase:
    return database.db

async def get_pagination(page: int = 1, page_size: int = 50) -> dict:
    max_page_size = 500
    actual_page_size = min(page_size, max_page_size)
    if page < 1:
        page = 1
    skip = (page - 1) * actual_page_size
    return {
        "page": page,
        "page_size": actual_page_size,
        "skip": skip,
        "limit": actual_page_size
    }