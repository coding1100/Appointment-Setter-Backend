"""
Core utility functions for common operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi.responses import JSONResponse


def get_current_timestamp() -> str:
    """
    Get current UTC timestamp in ISO format.

    Returns:
        ISO format timestamp string (e.g., "2024-01-01T12:00:00+00:00")
    """
    return datetime.now(timezone.utc).isoformat()


def add_cors_headers(response: JSONResponse) -> JSONResponse:
    """
    Add CORS headers to a JSONResponse.

    Note: CORS middleware should handle this automatically, but this ensures
    headers are present in exception handlers where middleware might not apply.

    Args:
        response: JSONResponse to add headers to

    Returns:
        Response with CORS headers added
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


def add_timestamps(data: Dict[str, Any], include_created: bool = True, include_updated: bool = True) -> Dict[str, Any]:
    """
    Add created_at and/or updated_at timestamps to a dictionary.

    Args:
        data: Dictionary to add timestamps to
        include_created: Whether to add created_at timestamp
        include_updated: Whether to add updated_at timestamp

    Returns:
        Dictionary with timestamps added
    """
    timestamp = get_current_timestamp()
    if include_created:
        data["created_at"] = timestamp
    if include_updated:
        data["updated_at"] = timestamp
    return data


def add_updated_timestamp(update_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add updated_at timestamp to update data dictionary.

    Args:
        update_data: Dictionary to add updated_at to

    Returns:
        Dictionary with updated_at timestamp added
    """
    update_data["updated_at"] = get_current_timestamp()
    return update_data
