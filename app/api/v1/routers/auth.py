"""
Authentication API routes using Firebase.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header

from app.api.v1.schemas.auth import (
    UserCreate,
    UserUpdate,
    UserLogin,
    TokenResponse,
    UserResponse,
    PasswordChange,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PermissionCreate,
    RoleCreate,
    LogoutRequest,
)
from app.api.v1.services.auth import auth_service
from app.core.security import SecurityService
from app.core.config import SECRET_KEY
from jose import JWTError, jwt
from fastapi import Depends

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


@router.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, request: Request):
    """Register a new user."""
    try:
        # Check if user already exists
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        # Create user
        user = await auth_service.create_user(user_data)

        return UserResponse(
            id=user.get("id", ""),
            email=user.get("email", ""),
            username=user.get("username", ""),
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name", ""),
            role=user.get("role", "user"),
            status=user.get("status", "active"),
            tenant_id=user.get("tenant_id"),
            is_email_verified=user.get("is_email_verified", False),
            last_login=user.get("last_login"),
            created_at=datetime.fromisoformat(
                user.get("created_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                user.get("updated_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=TokenResponse)
async def login_user(login_data: UserLogin, request: Request):
    """Authenticate user and return tokens."""
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

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=1800,  # 30 minutes
            user=UserResponse(
                id=user.get("id", ""),
                email=user.get("email", ""),
                username=user.get("username", ""),
                first_name=user.get("first_name", ""),
                last_name=user.get("last_name", ""),
                role=user.get("role", "user"),
                status=user.get("status", "active"),
                tenant_id=user.get("tenant_id"),
                is_email_verified=user.get("is_email_verified", False),
                last_login=user.get("last_login"),
                created_at=datetime.fromisoformat(
                    user.get("created_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
                ),
                updated_at=datetime.fromisoformat(
                    user.get("updated_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
                ),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {str(e)}")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, request: Request):
    """Refresh access token using refresh token."""
    try:
        # Verify refresh token
        payload = auth_service.verify_token(refresh_token, "refresh")
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        # Get user session
        session = await auth_service.get_user_session(refresh_token)
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

        # Create new access token
        new_access_token = auth_service.create_access_token({"sub": user_id})

        return TokenResponse(
            access_token=new_access_token, refresh_token=refresh_token, token_type="bearer", expires_in=1800  # 30 minutes
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Token refresh failed: {str(e)}")


@router.post("/logout")
async def logout_user(logout_data: LogoutRequest, request: Request):
    """Logout user and revoke session."""
    try:
        # Revoke user session
        await auth_service.revoke_user_session(logout_data.refresh_token)

        return {"message": "Successfully logged out"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Logout failed: {str(e)}")


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    """Get current user information."""
    try:
        return UserResponse(
            id=current_user.get("id", ""),
            email=current_user.get("email", ""),
            username=current_user.get("username", ""),
            first_name=current_user.get("first_name", ""),
            last_name=current_user.get("last_name", ""),
            role=current_user.get("role", "user"),
            status=current_user.get("status", "active"),
            tenant_id=current_user.get("tenant_id"),
            is_email_verified=current_user.get("is_email_verified", False),
            last_login=current_user.get("last_login"),
            created_at=datetime.fromisoformat(current_user["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(current_user["updated_at"].replace("Z", "+00:00")),
        )

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
        user_responses = []
        for user in users:
            user_responses.append(
                UserResponse(
                    id=user.get("id", ""),
                    email=user.get("email", ""),
                    username=user.get("username", ""),
                    first_name=user.get("first_name", ""),
                    last_name=user.get("last_name", ""),
                    role=user.get("role", "user"),
                    status=user.get("status", "active"),
                    tenant_id=user.get("tenant_id"),
                    is_email_verified=user.get("is_email_verified", False),
                    last_login=user.get("last_login"),
                    created_at=datetime.fromisoformat(
                        user.get("created_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
                    ),
                    updated_at=datetime.fromisoformat(
                        user.get("updated_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
                    ),
                )
            )

        return user_responses

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list users: {str(e)}")


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    """Get user by ID (admin only)."""
    try:
        user = await auth_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return UserResponse(
            id=user.get("id", ""),
            email=user.get("email", ""),
            username=user.get("username", ""),
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name", ""),
            role=user.get("role", "user"),
            status=user.get("status", "active"),
            tenant_id=user.get("tenant_id"),
            is_email_verified=user.get("is_email_verified", False),
            last_login=user.get("last_login"),
            created_at=datetime.fromisoformat(
                user.get("created_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                user.get("updated_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
        )

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

        return UserResponse(
            id=updated_user.get("id", ""),
            email=updated_user.get("email", ""),
            username=updated_user.get("username", ""),
            first_name=updated_user.get("first_name", ""),
            last_name=updated_user.get("last_name", ""),
            role=updated_user.get("role", "user"),
            status=updated_user.get("status", "active"),
            tenant_id=updated_user.get("tenant_id"),
            is_email_verified=updated_user.get("is_email_verified", False),
            last_login=updated_user.get("last_login"),
            created_at=datetime.fromisoformat(
                updated_user.get("created_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                updated_user.get("updated_at", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update user: {str(e)}")
