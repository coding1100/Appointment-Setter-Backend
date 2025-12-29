"""
Tenant management API routes using Firebase.
"""

import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.routers.auth import get_current_user_from_token, require_admin_role, verify_tenant_access
from app.api.v1.schemas.tenant import (
    AgentSettingsCreate,
    AgentSettingsUpdate,
    BusinessInfoCreate,
    BusinessInfoUpdate,
    ServiceTypeCreate,
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)
from app.api.v1.services.auth import auth_service
from app.api.v1.services.tenant import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


# Match login endpoint pattern - use specific path without trailing slash
# This avoids redirects and matches how /api/v1/auth/login works
@router.post("", response_model=TenantResponse)
async def create_tenant(tenant_data: TenantCreate, current_user: Dict = Depends(get_current_user_from_token)):
    """Create a new tenant. Requires admin role."""
    require_admin_role(current_user)
    try:
        tenant = await tenant_service.create_tenant(tenant_data)

        from app.core.response_mappers import to_tenant_response

        return to_tenant_response(tenant)

    except ValueError as e:
        # Duplicate tenant (same name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create tenant: {str(e)}")


# Match login endpoint pattern - use specific path without trailing slash
@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user_from_token),
):
    """List tenants with pagination. Requires admin role."""
    require_admin_role(current_user)
    try:
        tenants = await tenant_service.list_tenants(limit, offset)

        from app.core.response_mappers import to_tenant_response

        return [to_tenant_response(tenant) for tenant in tenants]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list tenants: {str(e)}")


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """Get tenant by ID."""
    verify_tenant_access(current_user, tenant_id)
    try:
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        from app.core.response_mappers import to_tenant_response

        return to_tenant_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get tenant: {str(e)}")


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: str, tenant_data: TenantUpdate, current_user: Dict = Depends(get_current_user_from_token)):
    """Update tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        tenant = await tenant_service.update_tenant(tenant_id, tenant_data)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        return TenantResponse(
            id=tenant["id"],
            name=tenant["name"],
            owner_email=tenant.get("owner_email"),
            created_at=tenant["created_at"],
            updated_at=tenant["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update tenant: {str(e)}")


@router.post("/{tenant_id}/business-info")
async def create_business_info(
    tenant_id: str, business_data: BusinessInfoCreate, current_user: Dict = Depends(get_current_user_from_token)
):
    """Create business information for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        business_info = await tenant_service.create_business_config(tenant_id, business_data)

        return {"message": "Business information created successfully", "business_info": business_info}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create business info: {str(e)}"
        )


@router.get("/{tenant_id}/business-info")
async def get_business_info(tenant_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """Get business information for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        business_info = await tenant_service.get_business_config(tenant_id)
        if not business_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business information not found")

        return business_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get business info: {str(e)}")


@router.put("/{tenant_id}/business-info")
async def update_business_info(
    tenant_id: str, business_data: BusinessInfoCreate, current_user: Dict = Depends(get_current_user_from_token)
):
    """Update business information for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        business_info = await tenant_service.update_business_config(tenant_id, business_data)
        if not business_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business information not found")

        return {"message": "Business information updated successfully", "business_info": business_info}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update business info: {str(e)}"
        )


@router.post("/{tenant_id}/agent-settings")
async def create_agent_settings(
    tenant_id: str, agent_data: AgentSettingsCreate, current_user: Dict = Depends(get_current_user_from_token)
):
    """Create agent settings for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        agent_settings = await tenant_service.create_agent_settings(tenant_id, agent_data)

        return {"message": "Agent settings created successfully", "agent_settings": agent_settings}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create agent settings: {str(e)}"
        )


@router.get("/{tenant_id}/agent-settings")
async def get_agent_settings(tenant_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """Get agent settings for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        agent_settings = await tenant_service.get_agent_settings(tenant_id)
        if not agent_settings:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent settings not found")

        return agent_settings

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get agent settings: {str(e)}"
        )


@router.put("/{tenant_id}/agent-settings")
async def update_agent_settings(
    tenant_id: str, agent_data: AgentSettingsCreate, current_user: Dict = Depends(get_current_user_from_token)
):
    """Update agent settings for a tenant."""
    verify_tenant_access(current_user, tenant_id)
    try:
        agent_settings = await tenant_service.update_agent_settings(tenant_id, agent_data)
        if not agent_settings:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent settings not found")

        return {"message": "Agent settings updated successfully", "agent_settings": agent_settings}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update agent settings: {str(e)}"
        )


# Note: Twilio integration endpoints have been moved to /api/v1/twilio-integration
# Use the dedicated twilio_integration router for all Twilio operations



