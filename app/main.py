"""
ISP Billing System - FastAPI Application Entry Point.
Phase 1: Foundation with health checks, logging, MongoDB, security middleware.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time

from app.core.config import settings
from app.core.database import database
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging, get_logger
from app.utils.helpers import success_response

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers.pop("Server", None)
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.time()
        logger.info(f"Request started: {request.method} {request.url.path}")
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"Request completed: {request.method} {request.url.path} - {response.status_code} in {duration_ms:.2f}ms")
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path in ["/health", "/health/live", "/health/ready"]:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        if client_ip in self.requests:
            self.requests[client_ip] = [ts for ts in self.requests[client_ip] if now - ts < self.window_seconds]
        request_count = len(self.requests.get(client_ip, []))
        if request_count >= self.max_requests:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "message": "Rate limit exceeded. Please try again later.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "details": {"limit": self.max_requests, "window_seconds": self.window_seconds}
                },
                headers={"Retry-After": str(self.window_seconds)}
            )
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        self.requests[client_ip].append(now)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} - Environment: {settings.app_env}")
    setup_logging(log_level=settings.log_level, environment=settings.app_env)
    try:
        await database.connect()
        logger.info("Application startup complete")
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    yield
    logger.info("Application shutting down...")
    await database.disconnect()
    logger.info("Shutdown complete")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Production-grade ISP Billing and Network Management System for Kenya.",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan
    )

    register_exception_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=settings.rate_limit_per_minute, window_seconds=60)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    allowed_hosts = settings.allowed_hosts if isinstance(settings.allowed_hosts, list) else [settings.allowed_hosts]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        return success_response(
            data={
                "app_name": settings.app_name,
                "version": "1.0.0",
                "environment": settings.app_env,
                "documentation": "/docs" if settings.debug else None,
                "health": "/health"
            },
            message="Welcome to ISP Billing System API"
        )

    # Health endpoints
    @app.get("/health", tags=["Health"])
    async def health_check():
        return success_response(
            data={
                "status": "healthy",
                "app_name": settings.app_name,
                "environment": settings.app_env,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            message="Application is healthy"
        )

    @app.get("/health/live", tags=["Health"])
    async def liveness_check():
        return success_response(
            data={"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()},
            message="Application is alive"
        )

    @app.get("/health/ready", tags=["Health"])
    async def readiness_check():
        db_health = await database.health_check()
        if db_health["status"] != "healthy":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "message": "Service not ready",
                    "error_code": "NOT_READY",
                    "details": {"database": db_health}
                }
            )
        return success_response(
            data={"status": "ready", "database": db_health, "timestamp": datetime.now(timezone.utc).isoformat()},
            message="Service is ready"
        )

    # System info (public, no secrets)
    @app.get("/api/v1/system/info", tags=["System"])
    async def system_info():
        return success_response(
            data={
                "name": settings.app_name,
                "environment": settings.app_env,
                "debug": settings.debug,
                "timezone": "Africa/Nairobi",
                "currency": "KES",
                "features": {
                    "authentication": False,
                    "billing": False,
                    "mpesa": False,
                    "radius": False,
                    "mikrotik": False,
                    "vouchers": False,
                    "customer_portal": False,
                    "notifications": False,
                }
            },
            message="System information"
        )

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )