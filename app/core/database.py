"""Async MongoDB database connection using Motor."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ServerSelectionTimeoutError

from app.core.config import settings
from app.core.exceptions import DatabaseConnectionError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Collections that will be used across the application
COLLECTIONS = [
    "users",
    "customers",
    "services",
    "subscriptions",
    "invoices",
    "payments",
    "vouchers",
    "radius_sessions",
    "audit_logs",
    "sites",
    "routers",
]

# Indexes to create upfront for performance
INDEXES = {
    "users": [
        {"keys": [("email", 1)], "unique": True},
        {"keys": [("username", 1)], "unique": True},
        {"keys": [("role", 1)]},
        {"keys": [("status", 1)]},
        {"keys": [("created_at", -1)]},
    ],
    "customers": [
        {"keys": [("customer_code", 1)], "unique": True},
        {"keys": [("email", 1)]},
        {"keys": [("phone", 1)]},
        {"keys": [("status", 1)]},
        {"keys": [("customer_type", 1)]},
        {"keys": [("assigned_to", 1)]},
        {"keys": [("created_at", -1)]},
    ],
    "services": [
        {"keys": [("name", 1)], "unique": True},
        {"keys": [("status", 1)]},
    ],
    "subscriptions": [
        {"keys": [("customer_id", 1)]},
        {"keys": [("service_id", 1)]},
        {"keys": [("status", 1)]},
        {"keys": [("start_date", -1)]},
    ],
    "invoices": [
        {"keys": [("customer_id", 1)]},
        {"keys": [("invoice_number", 1)], "unique": True},
        {"keys": [("status", 1)]},
        {"keys": [("due_date", 1)]},
        {"keys": [("created_at", -1)]},
    ],
    "payments": [
        {"keys": [("customer_id", 1)]},
        {"keys": [("invoice_id", 1)]},
        {"keys": [("transaction_id", 1)], "unique": True},
        {"keys": [("payment_method", 1)]},
        {"keys": [("created_at", -1)]},
    ],
    "vouchers": [
        {"keys": [("code", 1)], "unique": True},
        {"keys": [("status", 1)]},
        {"keys": [("expiry_date", 1)]},
    ],
    "radius_sessions": [
        {"keys": [("username", 1)]},
        {"keys": [("nas_ip_address", 1)]},
        {"keys": [("start_time", -1)]},
        {"keys": [("status", 1)]},
    ],
    "audit_logs": [
        {"keys": [("user_id", 1)]},
        {"keys": [("action", 1)]},
        {"keys": [("resource", 1)]},
        {"keys": [("created_at", -1)]},
        {"keys": [("created_at", 1)], "expireAfterSeconds": 7776000},  # TTL: 90 days
    ],
    "sites": [
        {"keys": [("name", 1)], "unique": True},
        {"keys": [("status", 1)]},
    ],
    "routers": [
        {"keys": [("name", 1)], "unique": True},
        {"keys": [("ip_address", 1)], "unique": True},
        {"keys": [("site_id", 1)]},
        {"keys": [("status", 1)]},
    ],
}


class Database:
    """Singleton database manager."""

    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db: AsyncIOMotorDatabase = None

    async def connect(self) -> None:
        """Establish MongoDB connection with pooling."""
        try:
            connection_options = {
                "maxPoolSize": 50,
                "minPoolSize": 10,
                "serverSelectionTimeoutMS": 30000,
                "connectTimeoutMS": 30000,
                "socketTimeoutMS": 30000,
            }

            # Detect Atlas connection
            if "mongodb+srv" in settings.mongodb_url or "cluster" in settings.mongodb_url:
                logger.info("Detected MongoDB Atlas connection - using extended timeouts")
                connection_options["tls"] = True

            self.client = AsyncIOMotorClient(
                settings.mongodb_url,
                **connection_options,
            )
            self.db = self.client[settings.database_name]

            # Verify connection
            await self.client.admin.command("ping")
            logger.info(f"MongoDB connected: {settings.database_name}")

            # Create indexes
            await self._create_indexes()

        except ServerSelectionTimeoutError as e:
            logger.critical(f"MongoDB connection timeout: {e}")
            raise DatabaseConnectionError(f"Could not connect to MongoDB: {e}")
        except Exception as e:
            logger.critical(f"MongoDB connection failed: {e}")
            raise DatabaseConnectionError(f"Database connection error: {e}")

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

    async def is_healthy(self) -> bool:
        """Check if database connection is alive."""
        try:
            if self.client is None:
                return False
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False

    async def _create_indexes(self) -> None:
        """Create all collection indexes upfront."""
        for collection_name, indexes in INDEXES.items():
            collection = self.db[collection_name]
            for index in indexes:
                try:
                    keys = index.pop("keys")
                    await collection.create_index(keys, **index)
                except Exception as e:
                    logger.warning(f"Index creation warning for {collection_name}: {e}")
        logger.info("Database indexes created/verified")


# Global database instance
database = Database()