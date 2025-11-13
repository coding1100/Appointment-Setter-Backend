"""
Tenant management API routes using Firebase.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.api.v1.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    BusinessInfoCreate,
    BusinessInfoUpdate,
    AgentSettingsCreate,
    AgentSettingsUpdate,
    ServiceTypeCreate,
)
from app.api.v1.services.tenant import tenant_service
from app.api.v1.services.auth import auth_service
from app.core.security import SecurityService

router = APIRouter(prefix="/tenants", tags=["tenants"])


def get_security_service() -> SecurityService:
    """Get security service instance."""
    return SecurityService()


# Match login endpoint pattern - use specific path without trailing slash
# This avoids redirects and matches how /api/v1/auth/login works
@router.post("", response_model=TenantResponse)
async def create_tenant(tenant_data: TenantCreate):
    """Create a new tenant."""
    try:
        tenant = await tenant_service.create_tenant(tenant_data)

        return TenantResponse(
            id=tenant["id"],
            name=tenant["name"],
            timezone=tenant["timezone"],
            status=tenant["status"],
            created_at=tenant["created_at"],
            updated_at=tenant["updated_at"],
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create tenant: {str(e)}")


# Match login endpoint pattern - use specific path without trailing slash
@router.get("", response_model=List[TenantResponse])
async def list_tenants(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """List tenants with pagination."""
    try:
        tenants = await tenant_service.list_tenants(limit, offset)

        return [
            TenantResponse(
                id=tenant["id"],
                name=tenant["name"],
                timezone=tenant["timezone"],
                status=tenant["status"],
                created_at=tenant["created_at"],
                updated_at=tenant["updated_at"],
            )
            for tenant in tenants
        ]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list tenants: {str(e)}")


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str):
    """Get tenant by ID."""
    try:
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        return TenantResponse(
            id=tenant["id"],
            name=tenant["name"],
            timezone=tenant["timezone"],
            status=tenant["status"],
            created_at=tenant["created_at"],
            updated_at=tenant["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get tenant: {str(e)}")


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: str, tenant_data: TenantUpdate):
    """Update tenant."""
    try:
        tenant = await tenant_service.update_tenant(tenant_id, tenant_data)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        return TenantResponse(
            id=tenant["id"],
            name=tenant["name"],
            timezone=tenant["timezone"],
            status=tenant["status"],
            created_at=tenant["created_at"],
            updated_at=tenant["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update tenant: {str(e)}")


@router.post("/{tenant_id}/business-info")
async def create_business_info(tenant_id: str, business_data: BusinessInfoCreate):
    """Create business information for a tenant."""
    try:
        # Check if tenant exists
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        business_info = await tenant_service.create_business_config(tenant_id, business_data)

        return {"message": "Business information created successfully", "business_info": business_info}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create business info: {str(e)}"
        )


@router.get("/{tenant_id}/business-info")
async def get_business_info(tenant_id: str):
    """Get business information for a tenant."""
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
async def update_business_info(tenant_id: str, business_data: BusinessInfoCreate):
    """Update business information for a tenant."""
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
async def create_agent_settings(tenant_id: str, agent_data: AgentSettingsCreate):
    """Create agent settings for a tenant."""
    try:
        # Check if tenant exists
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        agent_settings = await tenant_service.create_agent_settings(tenant_id, agent_data)

        return {"message": "Agent settings created successfully", "agent_settings": agent_settings}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create agent settings: {str(e)}"
        )


@router.get("/{tenant_id}/agent-settings")
async def get_agent_settings(tenant_id: str):
    """Get agent settings for a tenant."""
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
async def update_agent_settings(tenant_id: str, agent_data: AgentSettingsCreate):
    """Update agent settings for a tenant."""
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


@router.post("/{tenant_id}/activate")
async def activate_tenant(tenant_id: str):
    """Activate a tenant."""
    try:
        success = await tenant_service.activate_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to activate tenant")

        return {"message": "Tenant activated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to activate tenant: {str(e)}")


@router.post("/{tenant_id}/deactivate")
async def deactivate_tenant(tenant_id: str):
    """Deactivate a tenant."""
    try:
        success = await tenant_service.deactivate_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to deactivate tenant")

        return {"message": "Tenant deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to deactivate tenant: {str(e)}")
