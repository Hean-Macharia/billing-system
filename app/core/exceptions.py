"""Custom exception hierarchy for the application."""
from typing import Any, Dict, Optional


class APIException(Exception):
    """Base exception for all API errors."""
    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"
    message: str = "An error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.message
        self.status_code = status_code or self.status_code
        self.error_code = error_code or self.error_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(APIException):
    """Raised when authentication fails (401)."""
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    message = "Authentication failed"


class AuthorizationError(APIException):
    """Raised when user lacks permission (403)."""
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
    message = "Access denied"


class NotFoundError(APIException):
    """Raised when a resource is not found (404)."""
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class ConflictError(APIException):
    """Raised when there's a resource conflict (409)."""
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


class ValidationError(APIException):
    """Raised when request validation fails (422)."""
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Validation failed"


class BadRequestError(APIException):
    """Raised for bad requests (400)."""
    status_code = 400
    error_code = "BAD_REQUEST"
    message = "Bad request"


class ServiceUnavailableError(APIException):
    """Raised when a service is unavailable (503)."""
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class DatabaseConnectionError(APIException):
    """Raised when database connection fails."""
    status_code = 503
    error_code = "DATABASE_CONNECTION_ERROR"
    message = "Failed to connect to database"