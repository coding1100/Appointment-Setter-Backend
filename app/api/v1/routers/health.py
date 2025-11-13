"""
Health check endpoints for monitoring and diagnostics.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import firebase_admin
import redis
from fastapi import APIRouter, status
from livekit import api as livekit_api

from app.core.config import ENVIRONMENT, LIVEKIT_URL, REDIS_URL

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


# Register both with and without trailing slash to handle Nginx redirects
# This ensures both /api/v1/health and /api/v1/health/ work
@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    Returns 200 OK if the service is running.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "AI Phone Scheduler API",
        "version": "1.0.0",
        "environment": ENVIRONMENT,
    }


@router.get("/detailed", status_code=status.HTTP_200_OK)
@router.get("/detailed/", status_code=status.HTTP_200_OK)
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check that tests external dependencies.
    Returns health status of all components.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "AI Phone Scheduler API",
        "version": "1.0.0",
        "environment": ENVIRONMENT,
        "components": {},
    }

    overall_healthy = True

    # Check Redis
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        health_status["components"]["redis"] = {"status": "healthy", "message": "Connected"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["components"]["redis"] = {"status": "unhealthy", "message": str(e)}
        overall_healthy = False

    # Check Firebase
    try:
        if firebase_admin._apps:
            health_status["components"]["firebase"] = {"status": "healthy", "message": "Initialized"}
        else:
            health_status["components"]["firebase"] = {"status": "unhealthy", "message": "Not initialized"}
            overall_healthy = False
    except Exception as e:
        logger.error(f"Firebase health check failed: {e}")
        health_status["components"]["firebase"] = {"status": "unhealthy", "message": str(e)}
        overall_healthy = False

    # Check LiveKit (basic URL validation)
    try:
        if LIVEKIT_URL:
            health_status["components"]["livekit"] = {"status": "configured", "message": "URL configured"}
        else:
            health_status["components"]["livekit"] = {"status": "not_configured", "message": "URL not set"}
    except Exception as e:
        logger.error(f"LiveKit health check failed: {e}")
        health_status["components"]["livekit"] = {"status": "error", "message": str(e)}

    # Set overall status
    health_status["status"] = "healthy" if overall_healthy else "degraded"

    return health_status


@router.get("/ready", status_code=status.HTTP_200_OK)
@router.get("/ready/", status_code=status.HTTP_200_OK)
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness probe for Kubernetes/container orchestration.
    Returns 200 if the service is ready to accept traffic.
    """
    # Check critical dependencies
    ready = True
    checks = {}

    # Check Redis
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False
        ready = False

    # Check Firebase
    try:
        checks["firebase"] = bool(firebase_admin._apps)
        if not checks["firebase"]:
            ready = False
    except Exception:
        checks["firebase"] = False
        ready = False

    if ready:
        return {"status": "ready", "checks": checks}
    else:
        return {"status": "not_ready", "checks": checks}


@router.get("/live", status_code=status.HTTP_200_OK)
@router.get("/live/", status_code=status.HTTP_200_OK)
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe for Kubernetes/container orchestration.
    Returns 200 if the service is alive (even if dependencies are down).
    """
    return {"status": "alive"}
