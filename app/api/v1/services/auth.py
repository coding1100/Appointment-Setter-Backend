"""
Authentication service for user management and JWT token handling using Firebase.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext

from app.api.v1.schemas.auth import LoginRequest, PasswordChangeRequest, UserCreate, UserUpdate
from app.core.async_redis import async_redis_client
from app.core.config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_REFRESH_TOKEN_EXPIRE_DAYS, SECRET_KEY
from app.core.utils import add_timestamps, add_updated_timestamp, get_current_timestamp
from app.services.firebase import firebase_service

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configure logging
logger = logging.getLogger(__name__)


class AuthService:
    """Service class for authentication operations using Firebase/Firestore."""

    def __init__(self):
        """Initialize auth service."""
        pass

    @staticmethod
    def _truncate_password_for_bcrypt(password: str) -> str:
        """Truncate password to 72 bytes for bcrypt compatibility.

        Bcrypt has a 72-byte limit. This method safely truncates
        passwords exceeding this limit while preserving UTF-8 encoding.
        """
        password_bytes = password.encode("utf-8")
        if len(password_bytes) <= 72:
            return password

        # Truncate to 72 bytes, ensuring we don't split multi-byte characters
        password_bytes = password_bytes[:72]
        # Remove any incomplete trailing bytes (continuation bytes without a start byte)
        while password_bytes and password_bytes[-1] & 0x80 and not (password_bytes[-1] & 0x40):
            password_bytes = password_bytes[:-1]

        return password_bytes.decode("utf-8", errors="ignore")

    # Password utilities
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        # Bcrypt has a 72-byte limit, truncate if necessary
        truncated_password = self._truncate_password_for_bcrypt(plain_password)
        return pwd_context.verify(truncated_password, hashed_password)

    async def verify_password_async(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password asynchronously to avoid blocking."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.verify_password, plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        # Bcrypt has a 72-byte limit, truncate if necessary
        truncated_password = self._truncate_password_for_bcrypt(password)
        return pwd_context.hash(truncated_password)

    # JWT token utilities
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != token_type:
                return None
            return payload
        except ExpiredSignatureError:
            return None
        except JWTError:
            return None

    # User management
    async def create_user(self, user_data: UserCreate) -> Dict[str, Any]:
        """Create a new user."""
        # Hash the password
        hashed_password = self.get_password_hash(user_data.password)

        # Prepare user data for Firebase
        user_dict = {
            "id": str(uuid.uuid4()),
            "email": user_data.email,
            "username": user_data.username,
            "hashed_password": hashed_password,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "full_name": f"{user_data.first_name} {user_data.last_name}",
            "role": user_data.role.value if user_data.role else "user",
            "status": "active",
            "is_active": True,
            "is_verified": False,
            "is_email_verified": False,
            "tenant_id": user_data.tenant_id,
            "last_login": None,
        }

        return await firebase_service.create_user(user_dict)

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        return await firebase_service.get_user_by_email(email)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return await firebase_service.get_user(user_id)

    async def list_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List users with pagination."""
        return await firebase_service.list_users(limit, offset)

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return await firebase_service.get_user(user_id)

    async def update_user(self, user_id: str, user_data: UserUpdate) -> Dict[str, Any]:
        """Update user."""
        update_data = {}
        add_updated_timestamp(update_data)

        if user_data.email:
            update_data["email"] = user_data.email
        if user_data.username:
            update_data["username"] = user_data.username
        if user_data.first_name:
            update_data["first_name"] = user_data.first_name
        if user_data.last_name:
            update_data["last_name"] = user_data.last_name
        if user_data.first_name and user_data.last_name:
            update_data["full_name"] = f"{user_data.first_name} {user_data.last_name}"
        if user_data.role:
            update_data["role"] = user_data.role.value
        if user_data.status:
            update_data["status"] = user_data.status.value
        if user_data.tenant_id:
            update_data["tenant_id"] = user_data.tenant_id

        return await firebase_service.update_user(user_id, update_data)

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user with email and password (optimized)."""
        user = await self.get_user_by_email(email)
        if not user:
            return None

        # Use async password verification to avoid blocking event loop
        if not await self.verify_password_async(password, user["hashed_password"]):
            return None

        if not user.get("is_active", False):
            return None

        return user

    async def change_password(self, user_id: str, password_data: PasswordChangeRequest) -> bool:
        """Change user password."""
        user = await self.get_user(user_id)
        if not user:
            return False

        # Verify current password
        if not self.verify_password(password_data.current_password, user["hashed_password"]):
            return False

        # Hash new password
        new_hashed_password = self.get_password_hash(password_data.new_password)

        # Update password
        update_data = {"hashed_password": new_hashed_password}
        add_updated_timestamp(update_data)
        await firebase_service.update_user(user_id, update_data)

        return True

    async def create_user_session(self, user_id: str, refresh_token: str) -> Dict[str, Any]:
        """
        Create a user session and store it in Redis.

        Session Storage:
        - Redis key: `session:{session_id}` - stores full session data
        - Redis key: `refresh_token:{token}` - maps refresh token to session_id for lookup
        - TTL matches refresh token expiry (JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        """
        import json

        session_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        ttl_seconds = int(JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)

        session_data = {
            "id": session_id,
            "user_id": user_id,
            "refresh_token": refresh_token,
            "is_active": True,
            "created_at": get_current_timestamp(),
            "expires_at": expires_at.isoformat(),
        }

        try:
            # Store session data
            await async_redis_client.setex(f"session:{session_id}", ttl_seconds, json.dumps(session_data))
            # Store refresh token mapping for lookup
            await async_redis_client.setex(f"refresh_token:{refresh_token}", ttl_seconds, session_id)
        except Exception as e:
            logger.error(f"Failed to store session in Redis: {e}", exc_info=True)
            logger.warning("Session storage failed, but continuing with session creation")

        return session_data

    async def get_user_session(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Get user session by refresh token from Redis.

        Looks up session_id from refresh_token mapping, then fetches full session data.
        Verifies session is active and not expired.
        """
        import json

        try:
            # Look up session_id from refresh_token
            session_id = await async_redis_client.get(f"refresh_token:{refresh_token}")
            if not session_id:
                return None

            # Get session data
            session_json = await async_redis_client.get(f"session:{session_id}")
            if not session_json:
                return None

            session_data = json.loads(session_json)

            # Verify session is active
            if not session_data.get("is_active", False):
                return None

            # Check expiration
            expires_at_str = session_data.get("expires_at")
            if expires_at_str:
                from app.core.response_mappers import parse_iso_timestamp

                expires_at = parse_iso_timestamp(expires_at_str)
                if not expires_at:
                    return None
                if datetime.now(timezone.utc) >= expires_at:
                    return None

            return session_data
        except Exception as e:
            logger.error(f"Failed to get session from Redis: {e}", exc_info=True)
            # Fallback: if Redis lookup fails, verify token directly (backward compatibility)
            payload = self.verify_token(refresh_token, "refresh")
            if payload:
                user_id = payload.get("sub")
                if user_id:
                    logger.warning("Session not found in Redis, using token verification fallback")
                    return {"user_id": user_id, "refresh_token": refresh_token}
            return None

    async def revoke_user_session(self, refresh_token: str) -> bool:
        """
        Revoke a user session by deleting it from Redis.

        Deletes both the session data and the refresh_token mapping.
        """
        try:
            # Get session_id from refresh_token mapping
            session_id = await async_redis_client.get(f"refresh_token:{refresh_token}")

            # Delete both keys
            keys_to_delete = [f"refresh_token:{refresh_token}"]
            if session_id:
                keys_to_delete.append(f"session:{session_id}")

            deleted = await async_redis_client.delete(*keys_to_delete)
            return deleted > 0
        except Exception as e:
            logger.error(f"Failed to revoke session in Redis: {e}", exc_info=True)
            return False

    async def get_user_permissions(self, user_id: str) -> List[str]:
        """Get user permissions."""
        user = await self.get_user(user_id)
        if not user:
            return []

        # For now, return basic permissions based on role
        role = user.get("role", "user")
        if role == "admin":
            return ["admin:all"]
        elif role == "tenant_admin":
            return ["tenant:manage", "appointment:manage", "user:view"]
        else:
            return ["appointment:view"]

    async def has_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has a specific permission."""
        permissions = await self.get_user_permissions(user_id)
        return permission in permissions or "admin:all" in permissions


# Global auth service instance
auth_service = AuthService()
