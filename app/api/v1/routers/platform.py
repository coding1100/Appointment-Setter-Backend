from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.routers.auth import get_current_user_from_token, require_admin_role
from app.api.v1.schemas.platform import PlatformAppAccessUpdateRequest, PlatformAppResponse, PlatformBootstrapResponse
from app.api.v1.services.auth import auth_service
from app.core.platform_apps import get_platform_app_catalog, resolve_allowed_app_ids, resolve_default_app_id, sanitize_app_ids
from app.core.response_mappers import to_user_response
from app.services.firebase import firebase_service

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/bootstrap", response_model=PlatformBootstrapResponse)
async def get_platform_bootstrap(current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    allowed_app_ids = resolve_allowed_app_ids(current_user)
    apps = [PlatformAppResponse(**app) for app in get_platform_app_catalog() if app["id"] in allowed_app_ids]
    return PlatformBootstrapResponse(
        user=to_user_response(current_user),
        allowed_app_ids=allowed_app_ids,
        default_app_id=resolve_default_app_id(current_user),
        apps=apps,
    )


@router.put("/users/{user_id}/app-access")
async def update_user_app_access(
    user_id: str,
    payload: PlatformAppAccessUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_from_token),
):
    require_admin_role(current_user)
    existing_user = await auth_service.get_user(user_id)
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    allowed_app_ids = sanitize_app_ids(payload.allowed_app_ids)
    if not allowed_app_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one allowed_app_id is required")

    default_app_id = payload.default_app_id if payload.default_app_id in allowed_app_ids else allowed_app_ids[0]
    await firebase_service.update_user(user_id, {"allowed_app_ids": allowed_app_ids, "default_app_id": default_app_id})
    updated_user = await auth_service.get_user(user_id)
    return {
        "user": to_user_response(updated_user),
        "allowed_app_ids": allowed_app_ids,
        "default_app_id": default_app_id,
    }
