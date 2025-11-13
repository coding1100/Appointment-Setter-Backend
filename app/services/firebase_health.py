"""
Firebase connection health check and connection pool management.
This helps prevent slow queries by pre-warming connections.
"""
import asyncio
import logging
from datetime import datetime, timezone
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
            
            # Perform a simple query to warm up the connection
            # This will trigger credential refresh if needed
            test_query = firebase_service.db.collection("_health").limit(1)
            await asyncio.to_thread(lambda: list(test_query.stream()))
            
            self.connection_pool_warm = True
            self.last_health_check = datetime.now(timezone.utc)
            logger.info("✅ Firebase connection warmed up successfully")
        except Exception as e:
            logger.warning(f"Failed to warm up Firebase connection: {e}")
            # Don't fail startup if warmup fails, but log it
    
    async def health_check(self) -> bool:
        """Check if Firebase connection is healthy."""
        try:
            from app.services.firebase import firebase_service
            
            # Simple ping query
            test_query = firebase_service.db.collection("_health").limit(1)
            await asyncio.to_thread(lambda: list(test_query.stream()))
            
            return True
        except Exception as e:
            logger.error(f"Firebase health check failed: {e}")
            return False

# Global instance
firebase_health = FirebaseHealth()

