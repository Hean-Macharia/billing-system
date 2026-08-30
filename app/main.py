"""FastAPI application entry point."""
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import database
from app.core.exceptions import (
    APIException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger, setup_logging
from app.utils.helpers import error_response

logger = get_logger(__name__)


class SecurityHeadersMiddleware:
    """Add security headers to all responses."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                extra_headers = [
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"content-security-policy", b"default-src 'self'"),
                ]
                message["headers"] = headers + extra_headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestTimingMiddleware:
    """Log request timing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.time()
        method = scope.get("method", "")
        path = scope.get("path", "")
        logger.info(f"Request started: {method} {path}")

        async def send_with_log(message):
            if message["type"] == "http.response.start":
                duration = (time.time() - start) * 1000
                status_code = message.get("status", 0)
                logger.info(f"Request completed: {method} {path} - {status_code} in {duration:.2f}ms")
            await send(message)

        await self.app(scope, receive, send_with_log)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    setup_logging()
    try:
        await database.connect()
        logger.info("Application startup complete")
        yield
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    finally:
        await database.disconnect()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )

    # Exception handlers
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(message=exc.message, error_code=exc.error_code, status_code=exc.status_code),
        )

    @app.exception_handler(AuthenticationError)
    async def auth_exception_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=error_response(message=exc.message, error_code="AUTHENTICATION_ERROR", status_code=status.HTTP_401_UNAUTHORIZED),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_exception_handler(request: Request, exc: AuthorizationError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_response(message=exc.message, error_code="AUTHORIZATION_ERROR", status_code=status.HTTP_403_FORBIDDEN),
        )

    @app.exception_handler(NotFoundError)
    async def not_found_exception_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(message=exc.message, error_code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND),
        )

    @app.exception_handler(ConflictError)
    async def conflict_exception_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=error_response(message=exc.message, error_code="CONFLICT", status_code=status.HTTP_409_CONFLICT),
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(message=exc.message, error_code="VALIDATION_ERROR", status_code=status.HTTP_422_UNPROCESSABLE_ENTITY),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(message="An internal server error occurred", error_code="INTERNAL_SERVER_ERROR", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR),
        )

    # ── ROUTERS ──
    from app.routes import auth, customers, services, subscriptions, invoices, payments
    from app.routes import mpesa
    from app.routes import radius as radius_admin
    from app.routes import radius_auth as radius_internal
    from app.routes import sites
    from app.api.v1 import system

    app.include_router(auth.router)
    app.include_router(customers.router)
    app.include_router(services.router)
    app.include_router(subscriptions.router)
    app.include_router(invoices.router)
    app.include_router(payments.router)
    app.include_router(mpesa.router)
    app.include_router(radius_admin.router)
    app.include_router(radius_internal.router)
    app.include_router(sites.router)
    app.include_router(system.router)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "success": True,
            "message": "Welcome to ISP Billing System",
            "data": {
                "name": settings.app_name,
                "version": settings.app_version,
                "environment": settings.app_env,
                "docs": "/docs" if settings.debug else None,
            },
        }

    @app.get("/health", tags=["Health"])
    async def health():
        return {
            "success": True,
            "message": "Application is healthy",
            "data": {
                "status": "healthy",
                "app_name": settings.app_name,
                "environment": settings.app_env,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    @app.get("/health/live", tags=["Health"])
    async def health_live():
        return {"success": True, "message": "Application is alive", "data": {"status": "alive"}}

    @app.get("/health/ready", tags=["Health"])
    async def health_ready():
        is_db_ok = await database.is_healthy()
        if not is_db_ok:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=error_response(message="Database not ready", error_code="NOT_READY", status_code=status.HTTP_503_SERVICE_UNAVAILABLE),
            )
        return {"success": True, "message": "Application is ready", "data": {"status": "ready", "database": "connected"}}

    return app


app = create_app()
