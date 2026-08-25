"""
Async MongoDB connection using Motor.
Optimized for both local MongoDB and MongoDB Atlas (mongodb+srv://).
"""
from typing import Optional, Dict
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import time

from app.core.config import settings
from app.core.exceptions import DatabaseConnectionError
from app.core.logging import get_logger

logger = get_logger(__name__)

class Database:
    _instance: Optional["Database"] = None
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self) -> None:
        try:
            # Atlas (mongodb+srv://) needs longer timeouts and TLS
            is_atlas = settings.mongodb_url.startswith("mongodb+srv://")

            client_kwargs = {
                "maxPoolSize": settings.mongodb_max_pool_size,
                "minPoolSize": settings.mongodb_min_pool_size,
                "maxIdleTimeMS": settings.mongodb_max_idle_time_ms,
                "retryWrites": True,
                "w": "majority",
            }

            if is_atlas:
                # Atlas-specific settings
                client_kwargs["serverSelectionTimeoutMS"] = 30000  # 30s for Atlas
                client_kwargs["connectTimeoutMS"] = 30000
                client_kwargs["socketTimeoutMS"] = 30000
                client_kwargs["tls"] = True
                logger.info("Detected MongoDB Atlas connection - using extended timeouts")
            else:
                # Local/dev settings
                client_kwargs["serverSelectionTimeoutMS"] = 5000

            self._client = AsyncIOMotorClient(
                settings.mongodb_url,
                **client_kwargs
            )

            await self._client.admin.command("ping")
            self._db = self._client[settings.database_name]
            logger.info(f"MongoDB connected: {settings.database_name}")
            await self._create_indexes()
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            logger.error(f"MongoDB connection failed: {e}")
            is_atlas = settings.mongodb_url.startswith("mongodb+srv://")
            hint = ""
            if is_atlas:
                hint = (
                    " Atlas connection failed. Check: "
                    "(1) Your IP is whitelisted in Atlas Network Access, "
                    "(2) Credentials are correct, "
                    "(3) Firewall allows outbound to port 27017, "
                    "(4) Atlas cluster is running."
                )
            raise DatabaseConnectionError(
                message=f"Unable to connect to database.{hint}",
                details={"url": settings.mongodb_url.replace("//", "//***:***@") if "@" in settings.mongodb_url else settings.mongodb_url}
            )

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB disconnected")

    async def _create_indexes(self) -> None:
        await self._db.health_checks.create_index("timestamp", expireAfterSeconds=86400)
        await self._db.health_checks.create_index([("check_type", 1), ("timestamp", -1)])

        await self._db.customers.create_index("customer_number", unique=True)
        await self._db.customers.create_index("phone")
        await self._db.customers.create_index("email")
        await self._db.customers.create_index("site_id")
        await self._db.customers.create_index("status")

        await self._db.services.create_index("customer_id")
        await self._db.services.create_index("username", unique=True, sparse=True)
        await self._db.services.create_index("site_id")

        await self._db.subscriptions.create_index("customer_id")
        await self._db.subscriptions.create_index("expiry_date")
        await self._db.subscriptions.create_index("status")

        await self._db.invoices.create_index("invoice_number", unique=True, sparse=True)
        await self._db.invoices.create_index("customer_id")
        await self._db.invoices.create_index("status")

        await self._db.payments.create_index("transaction_reference", unique=True, sparse=True)
        await self._db.payments.create_index("mpesa_receipt", unique=True, sparse=True)

        await self._db.vouchers.create_index("code", unique=True, sparse=True)
        await self._db.vouchers.create_index("batch_id")

        await self._db.radius_sessions.create_index("session_id", unique=True, sparse=True)
        await self._db.radius_sessions.create_index("username")
        await self._db.radius_sessions.create_index("start_time")

        await self._db.sites.create_index("site_code", unique=True, sparse=True)
        await self._db.routers.create_index("hostname", unique=True, sparse=True)
        await self._db.routers.create_index("site_id")

        logger.info("Database indexes created/verified")

    @property
    def client(self) -> AsyncIOMotorClient:
        if self._client is None:
            raise DatabaseConnectionError(message="Database not connected")
        return self._client

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise DatabaseConnectionError(message="Database not connected")
        return self._db

    async def health_check(self) -> Dict:
        try:
            start = time.time()
            await self._client.admin.command("ping")
            latency_ms = (time.time() - start) * 1000
            server_info = await self._client.server_info()
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "mongodb_version": server_info.get("version", "unknown"),
                "database_name": settings.database_name
            }
        except Exception as e:
            logger.error(f"DB health check failed: {e}")
            return {"status": "unhealthy", "error": str(e), "database_name": settings.database_name}


database = Database()

async def get_database() -> AsyncIOMotorDatabase:
    return database.db