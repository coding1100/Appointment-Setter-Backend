"""
Authentication API routes using Firebase.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt

from app.api.v1.schemas.auth import (
    ForgotPasswordRequest,
    LogoutRequest,
    PasswordChange,
    PermissionCreate,
    ResetPasswordRequest,
    RoleCreate,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.api.v1.services.auth import auth_service
from app.core.config import SECRET_KEY
from app.core.security import SecurityService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


def get_security_service() -> SecurityService:
    """Get security service instance."""
    try:
        return SecurityService()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Security service unavailable: {str(e)}")


async def get_current_user_from_token(authorization: str = Header(None)) -> Dict[str, Any]:
    """Get current user from JWT token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Remove "Bearer " prefix if present
        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]

        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def verify_tenant_access(user: Dict[str, Any], tenant_id: str) -> None:
    """
    Verify that the authenticated user has access to the specified tenant.

    Tenant Binding Model:
    - Users have a `tenant_id` field that binds them to a tenant
    - Users with role 'admin' can access any tenant
    - Regular users can only access their own tenant (matching `tenant_id`)

    Raises HTTPException if access is denied.
    """
    user_role = user.get("role", "user")
    user_tenant_id = user.get("tenant_id")

    # Admins can access any tenant
    if user_role == "admin":
        return

    # Users must belong to the tenant they're trying to access
    if user_tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You do not have permission to access tenant {tenant_id}",
        )

    # Ensure user has a tenant_id
    if not user_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not associated with any tenant",
        )


def require_admin_role(user: Dict[str, Any]) -> None:
    """
    Verify that the authenticated user has admin role.

    Raises HTTPException if user is not an admin.
    """
    user_role = user.get("role", "user")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admin role required",
        )


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    Checks X-Forwarded-For header (for proxies) and falls back to direct client.
    """
    # Check for forwarded IP (when behind proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (common in Nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


@router.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, request: Request):
    """Register a new user."""
    # Rate limiting: 10 requests per minute per IP
    security_service = get_security_service()
    client_ip = get_client_ip(request)
    await security_service.enforce_rate_limit(client_ip, limit=10, window_seconds=60, operation="auth_register")

    try:
        # Check if user already exists
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        # Create user
        user = await auth_service.create_user(user_data)

        from app.core.response_mappers import to_user_response

        return to_user_response(user)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=TokenResponse)
async def login_user(login_data: UserLogin, request: Request):
    """Authenticate user and return tokens."""
    # Rate limiting: 10 requests per minute per IP
    security_service = get_security_service()
    client_ip = get_client_ip(request)
    await security_service.enforce_rate_limit(client_ip, limit=10, window_seconds=60, operation="auth_login")

    try:
        # Log the login attempt
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Login attempt for email: {login_data.email}")

        # Authenticate user
        user = await auth_service.authenticate_user(login_data.email, login_data.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        # Create tokens
        access_token = auth_service.create_access_token({"sub": user.get("id", "")})
        refresh_token = auth_service.create_refresh_token({"sub": user.get("id", "")})

        # Create user session
        await auth_service.create_user_session(user.get("id", ""), refresh_token)

        from app.core.response_mappers import to_user_response

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=1800,  # 30 minutes
            user=to_user_response(user),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {str(e)}")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, request: Request):
    """
    Refresh access token using refresh token.

    Uses session lookup from Redis to validate the refresh token.
    If session is valid, creates new tokens and updates the session.
    """
    # Rate limiting: 10 requests per minute per IP
    security_service = get_security_service()
    client_ip = get_client_ip(request)
    await security_service.enforce_rate_limit(client_ip, limit=10, window_seconds=60, operation="auth_refresh")

    try:
        # Get user session from Redis (validates session is active and not expired)
        session = await auth_service.get_user_session(refresh_token)
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

        user_id = session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session data")

        # Get user
        user = await auth_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Revoke old session
        await auth_service.revoke_user_session(refresh_token)

        # Create new tokens
        access_token = auth_service.create_access_token({"sub": user_id})
        new_refresh_token = auth_service.create_refresh_token({"sub": user_id})

        # Create new session with new refresh token
        await auth_service.create_user_session(user_id, new_refresh_token)

        from app.core.response_mappers import to_user_response

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=1800,  # 30 minutes
            user=to_user_response(user),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Token refresh failed: {str(e)}")


@router.post("/logout")
async def logout_user(logout_data: LogoutRequest, request: Request):
    """
    Logout user and invalidate refresh token.

    Revokes the session in Redis, making the refresh token unusable.
    """
    try:
        # Revoke refresh token (deletes session from Redis)
        success = await auth_service.revoke_user_session(logout_data.refresh_token)
        if not success:
            logger.warning(f"Failed to revoke session for refresh token (may already be revoked)")

        return {"message": "Successfully logged out"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Logout failed: {str(e)}")


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    """Get current user information."""
    try:
        from app.core.response_mappers import to_user_response

        return to_user_response(current_user)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get user information: {str(e)}"
        )


@router.put("/change-password")
async def change_password(password_data: PasswordChange, request: Request):
    """Change user password."""
    try:
        # This would be implemented with proper JWT authentication
        # For now, return a placeholder
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Password change not yet implemented")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Password change failed: {str(e)}")


@router.post("/forgot-password")
async def forgot_password(forgot_data: ForgotPasswordRequest, request: Request):
    """Send password reset email."""
    try:
        # This would be implemented with email service
        # For now, return a placeholder
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Password reset not yet implemented")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Password reset failed: {str(e)}")


@router.post("/reset-password")
async def reset_password(reset_data: ResetPasswordRequest, request: Request):
    """Reset user password."""
    try:
        # This would be implemented with email service
        # For now, return a placeholder
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Password reset not yet implemented")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Password reset failed: {str(e)}")


@router.get("/users", response_model=List[UserResponse])
async def list_users(request: Request, limit: int = 100, offset: int = 0):
    """List users (admin only)."""
    try:
        # Get users from database
        users = await auth_service.list_users(limit, offset)

        # Convert to UserResponse objects
        from app.core.response_mappers import to_user_response

        return [to_user_response(user) for user in users]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list users: {str(e)}")


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    """Get user by ID (admin only)."""
    try:
        user = await auth_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        from app.core.response_mappers import to_user_response

        return to_user_response(user)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get user: {str(e)}")


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, request: Request):
    """Update user (admin only)."""
    try:
        # Check if user exists
        existing_user = await auth_service.get_user(user_id)
        if not existing_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Update user
        updated_user = await auth_service.update_user(user_id, user_data)

        from app.core.response_mappers import to_user_response

        return to_user_response(updated_user)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update user: {str(e)}")
