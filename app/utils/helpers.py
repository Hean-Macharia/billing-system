"""
Utility helpers for the ISP Billing System.
"""
from typing import Any, Dict, Optional, List


def success_response(
    data: Any = None,
    message: str = "Success",
    meta: Optional[Dict] = None
) -> Dict:
    response = {
        "success": True,
        "message": message,
    }
    if data is not None:
        response["data"] = data
    if meta is not None:
        response["meta"] = meta
    return response


def paginated_response(
    data: List[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "Success"
) -> Dict:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "success": True,
        "message": message,
        "data": data,
        "meta": {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
    }


def error_response(
    message: str,
    error_code: str,
    status_code: int = 500,
    details: Optional[Dict] = None
) -> Dict:
    response = {
        "success": False,
        "message": message,
        "error_code": error_code,
    }
    if details is not None:
        response["details"] = details
    return response