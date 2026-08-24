"""
Custom exceptions and global exception handlers.
"""
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class ISPBaseException(Exception):
    """Base exception for all ISP Billing System errors."""

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseConnectionError(ISPBaseException):
    def __init__(self, message: str = "Database connection failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="DATABASE_CONNECTION_ERROR",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details
        )


class ResourceNotFoundError(ISPBaseException):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class DuplicateResourceError(ISPBaseException):
    def __init__(self, message: str = "Resource already exists", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="DUPLICATE_RESOURCE",
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class ValidationError(ISPBaseException):
    def __init__(self, message: str = "Validation failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class AuthenticationError(ISPBaseException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationError(ISPBaseException):
    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


def create_error_response(
    message: str,
    error_code: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None
) -> JSONResponse:
    content = {
        "success": False,
        "message": message,
        "error_code": error_code,
    }
    if details:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


async def isp_exception_handler(request: Request, exc: ISPBaseException) -> JSONResponse:
    return create_error_response(
        message=exc.message,
        error_code=exc.error_code,
        status_code=exc.status_code,
        details=exc.details
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    return create_error_response(
        message="Request validation failed",
        error_code="VALIDATION_ERROR",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors}
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return create_error_response(
        message="An internal server error occurred",
        error_code="INTERNAL_SERVER_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={}
    )


def register_exception_handlers(app):
    app.add_exception_handler(ISPBaseException, isp_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)