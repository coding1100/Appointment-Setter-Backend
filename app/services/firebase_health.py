"""
Firebase connection health check and connection pool management.
This helps prevent slow queries by pre-warming connections.
"""

import asyncio
import logging
from app.core.utils import get_current_timestamp
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)


class FirebaseHealth:
    """Maintains Firebase connection health."""

    def __init__(self):
        self.last_health_check = None
        self.connection_pool_warm = False

    async def warm_up_connection(self):
        """Pre-warm Firebase connection to avoid first-query delay."""
        try:
            from app.services.firebase import firebase_service

            # Use canonical service's health check method
            is_healthy = await firebase_service.health_check()
            if is_healthy:
                self.connection_pool_warm = True
                self.last_health_check = get_current_timestamp()
                logger.info("✅ Firebase connection warmed up successfully")
            else:
                logger.warning("Firebase health check returned False during warmup")
        except Exception as e:
            logger.warning(f"Failed to warm up Firebase connection: {e}")
            # Don't fail startup if warmup fails, but log it

    async def health_check(self) -> bool:
        """Check if Firebase connection is healthy."""
        try:
            from app.services.firebase import firebase_service

            # Use canonical service's health check method
            return await firebase_service.health_check()
        except Exception as e:
            logger.error(f"Firebase health check failed: {e}")
            return False


# Global instance
firebase_health = FirebaseHealth()
