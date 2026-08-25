"""Standardized API response utilities."""
from typing import Any, Dict, List, Optional


def success_response(
    message: str = "Success",
    data: Any = None,
    status_code: int = 200,
) -> Dict[str, Any]:
    """Build a standardized success response."""
    response = {
        "success": True,
        "message": message,
        "data": data,
    }
    return response


def error_response(
    message: str = "An error occurred",
    error_code: str = "INTERNAL_SERVER_ERROR",
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standardized error response."""
    response = {
        "success": False,
        "message": message,
        "error_code": error_code,
    }
    if details:
        response["details"] = details
    return response


def paginated_response(
    data: List[Any],
    total: int,
    page: int,
    limit: int,
    message: str = "Data retrieved successfully",
) -> Dict[str, Any]:
    """Build a standardized paginated response."""
    total_pages = (total + limit - 1) // limit if limit > 0 else 0
    return {
        "success": True,
        "message": message,
        "data": data,
        "meta": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }