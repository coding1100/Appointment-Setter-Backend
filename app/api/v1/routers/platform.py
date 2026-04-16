"""
Platform API routes.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.v1.routers.auth import get_current_user_from_token, require_admin_role
from app.api.v1.services.auth import auth_service
from app.core.platform_apps import (
    get_platform_apps,
    normalize_allowed_app_ids,
    resolve_user_allowed_app_ids,
    resolve_user_default_app_id,
)

router = APIRouter(prefix="/platform", tags=["platform"])


class PlatformAppResponse(BaseModel):
    id: str
    slug: str
    label: str
    default_route: str
    icon_key: str
    description: str


class PlatformBootstrapUser(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    allowed_app_ids: List[str] = Field(default_factory=list)
    default_app_id: str


class PlatformBootstrapResponse(BaseModel):
    user: PlatformBootstrapUser
    apps: List[PlatformAppResponse]
    allowed_app_ids: List[str]
    default_app_id: str
    permissions: List[str]


class UserAppAccessUpdateRequest(BaseModel):
    allowed_app_ids: List[str] = Field(default_factory=list)
    default_app_id: Optional[str] = None


class UserAppAccessUpdateResponse(BaseModel):
    user_id: str
    allowed_app_ids: List[str]
    default_app_id: str


@router.get("/bootstrap", response_model=PlatformBootstrapResponse)
async def get_platform_bootstrap(current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    allowed_app_ids = resolve_user_allowed_app_ids(current_user)
    default_app_id = resolve_user_default_app_id(current_user, allowed_app_ids)
    permissions = await auth_service.get_user_permissions(str(current_user.get("id", "")))

    return PlatformBootstrapResponse(
        user=PlatformBootstrapUser(
            id=str(current_user.get("id", "")),
            email=current_user.get("email", ""),
            first_name=current_user.get("first_name", ""),
            last_name=current_user.get("last_name", ""),
            role=str(current_user.get("role", "user")),
            allowed_app_ids=allowed_app_ids,
            default_app_id=default_app_id,
        ),
        apps=[PlatformAppResponse(**app) for app in get_platform_apps()],
        allowed_app_ids=allowed_app_ids,
        default_app_id=default_app_id,
        permissions=permissions,
    )


@router.put("/users/{user_id}/app-access", response_model=UserAppAccessUpdateResponse)
async def update_user_app_access(
    user_id: str,
    payload: UserAppAccessUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_from_token),
):
    require_admin_role(current_user)

    target_user = await auth_service.get_user(user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    allowed_app_ids = normalize_allowed_app_ids(payload.allowed_app_ids)
    if not allowed_app_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allowed_app_ids must contain at least one valid app id",
        )

    default_app_id = payload.default_app_id or target_user.get("default_app_id")
    if not default_app_id or default_app_id not in allowed_app_ids:
        default_app_id = allowed_app_ids[0]

    update_data = {
        "allowed_app_ids": allowed_app_ids,
        "default_app_id": default_app_id,
    }
    await auth_service.update_user_fields(user_id, update_data)

    return UserAppAccessUpdateResponse(
        user_id=user_id,
        allowed_app_ids=allowed_app_ids,
        default_app_id=default_app_id,
    )
