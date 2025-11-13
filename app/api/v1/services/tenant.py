"""
Tenant service layer for business logic using Supabase.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.v1.schemas.tenant import (
    AgentPolicyCreate,
    AgentSettingsCreate,
    BusinessInfoCreate,
    ServiceTypeCreate,
    TenantCreate,
    TenantUpdate,
    TwilioIntegrationCreate,
)
from app.core.prompts import prompt_map
from app.services.firebase import firebase_service


class TenantService:
    """Service class for tenant operations using Firebase."""

    def __init__(self):
        """Initialize tenant service."""
        pass

    async def create_tenant(self, tenant_data: TenantCreate) -> Dict[str, Any]:
        """Create a new tenant."""
        tenant_dict = {
            "id": str(uuid.uuid4()),
            "name": tenant_data.name,
            "timezone": tenant_data.timezone,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        return await firebase_service.create_tenant(tenant_dict)

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID."""
        return await firebase_service.get_tenant(tenant_id)

    async def update_tenant(self, tenant_id: str, tenant_data: TenantUpdate) -> Optional[Dict[str, Any]]:
        """Update tenant basic info."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if tenant_data.name:
            update_data["name"] = tenant_data.name
        if tenant_data.timezone:
            update_data["timezone"] = tenant_data.timezone

        return await firebase_service.update_tenant(tenant_id, update_data)

    async def list_tenants(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List tenants with pagination."""
        return await firebase_service.list_tenants(limit, offset)

    async def create_business_config(self, tenant_id: str, business_data: BusinessInfoCreate) -> Dict[str, Any]:
        """Create business configuration for a tenant."""
        business_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "business_name": business_data.business_name,
            "contact_email": business_data.contact_email,
            "contact_phone": business_data.contact_phone,
            "address": business_data.address,
            "website": business_data.website,
            "description": business_data.description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store in Firebase Firestore
        result = await firebase_service.create_business_config(business_dict)
        return result

    async def get_business_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get business configuration for a tenant."""
        return await firebase_service.get_business_config(tenant_id)

    async def update_business_config(self, tenant_id: str, business_data: BusinessInfoCreate) -> Optional[Dict[str, Any]]:
        """Update business configuration for a tenant."""
        update_data = {
            "business_name": business_data.business_name,
            "contact_email": business_data.contact_email,
            "contact_phone": business_data.contact_phone,
            "address": business_data.address,
            "website": business_data.website,
            "description": business_data.description,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        return await firebase_service.update_business_config(tenant_id, update_data)

    async def create_agent_settings(self, tenant_id: str, agent_data: AgentSettingsCreate) -> Dict[str, Any]:
        """Create agent settings for a tenant."""
        agent_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "service_type": agent_data.service_type,
            "agent_name": agent_data.agent_name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store in Firebase Firestore
        result = await firebase_service.create_agent_settings(agent_dict)
        return result

    async def get_agent_settings(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get agent settings for a tenant."""
        return await firebase_service.get_agent_settings(tenant_id)

    async def update_agent_settings(self, tenant_id: str, agent_data: AgentSettingsCreate) -> Optional[Dict[str, Any]]:
        """Update agent settings for a tenant."""
        update_data = {
            "service_type": agent_data.service_type,
            "agent_name": agent_data.agent_name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        return await firebase_service.update_agent_settings(tenant_id, update_data)

    async def create_twilio_integration(self, tenant_id: str, twilio_data: TwilioIntegrationCreate) -> Dict[str, Any]:
        """Create Twilio integration for a tenant."""
        twilio_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "phone_number": twilio_data.phone_number,
            "webhook_url": twilio_data.webhook_url,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store in Firebase Firestore
        result = await firebase_service.create_twilio_integration(twilio_dict)
        return result

    async def get_twilio_integration(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get Twilio integration for a tenant."""
        return await firebase_service.get_twilio_integration(tenant_id)

    async def update_twilio_integration(
        self, tenant_id: str, twilio_data: TwilioIntegrationCreate
    ) -> Optional[Dict[str, Any]]:
        """Update Twilio integration for a tenant."""
        update_data = {
            "phone_number": twilio_data.phone_number,
            "webhook_url": twilio_data.webhook_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        return await firebase_service.update_twilio_integration(tenant_id, update_data)

    async def activate_tenant(self, tenant_id: str) -> bool:
        """Activate a tenant."""
        update_data = {"status": "active", "updated_at": datetime.now(timezone.utc).isoformat()}

        result = await firebase_service.update_tenant(tenant_id, update_data)
        return result is not None

    async def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant."""
        update_data = {"status": "inactive", "updated_at": datetime.now(timezone.utc).isoformat()}

        result = await firebase_service.update_tenant(tenant_id, update_data)
        return result is not None

    def get_prompt_for_service_type(self, service_type: str) -> str:
        """Get the appropriate prompt for a service type."""
        return prompt_map.get(service_type, prompt_map["Home Services"])


# Global tenant service instance
tenant_service = TenantService()
