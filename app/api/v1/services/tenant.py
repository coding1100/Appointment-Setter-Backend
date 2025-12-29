"""
Tenant service layer for business logic using Firebase/Firestore.
"""

import uuid
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
from app.core.utils import add_timestamps, add_updated_timestamp
from app.services.firebase import firebase_service

class TenantService:
    """Service class for tenant operations using Firebase."""

    def __init__(self):
        """Initialize tenant service."""
        pass

    async def create_tenant(self, tenant_data: TenantCreate) -> Dict[str, Any]:
        """Create a new tenant."""
        # Normalize name for case-insensitive uniqueness
        normalized_name = tenant_data.name.strip()
        normalized_name_lower = normalized_name.lower()

        # Prevent duplicates by name (case-insensitive)
        existing_by_lower = await firebase_service.get_tenant_by_name_lower(normalized_name_lower)
        if existing_by_lower:
            raise ValueError(f"Tenant already exists with name '{normalized_name}'")

        tenant_dict = {
            "id": str(uuid.uuid4()),
            "name": normalized_name,
            "name_lower": normalized_name_lower,
            "owner_email": tenant_data.owner_email.strip(),
        }
        add_timestamps(tenant_dict)

        return await firebase_service.create_tenant(tenant_dict)

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID (with caching)."""
        from app.core.cache import get_cached_tenant, set_cached_tenant

        # Check cache first
        cached_tenant = await get_cached_tenant(tenant_id)
        if cached_tenant:
            return cached_tenant

        # Cache miss: fetch from Firebase
        tenant = await firebase_service.get_tenant(tenant_id)
        if tenant:
            # Store in cache
            await set_cached_tenant(tenant_id, tenant)

        return tenant

    async def update_tenant(self, tenant_id: str, tenant_data: TenantUpdate) -> Optional[Dict[str, Any]]:
        """Update tenant basic info."""
        from app.core.cache import invalidate_tenant_cache

        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        update_data = {}
        add_updated_timestamp(update_data)

        update_data["name"] = tenant_data.name
        update_data["owner_email"] = tenant_data.owner_email.strip()

        result = await firebase_service.update_tenant(tenant_id, update_data)

        # Invalidate cache on update
        if result:
            await invalidate_tenant_cache(tenant_id)

        return result

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
        }
        add_timestamps(business_dict)

        # Store in Firebase Firestore
        result = await firebase_service.create_business_config(business_dict)
        return result

    async def get_business_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get business configuration for a tenant (with caching)."""
        from app.core.cache import get_cached_business_config, set_cached_business_config

        # Check cache first
        cached_config = await get_cached_business_config(tenant_id)
        if cached_config:
            return cached_config

        # Cache miss: fetch from Firebase
        config = await firebase_service.get_business_config(tenant_id)
        if config:
            # Store in cache
            await set_cached_business_config(tenant_id, config)

        return config

    async def update_business_config(self, tenant_id: str, business_data: BusinessInfoCreate) -> Optional[Dict[str, Any]]:
        """Update business configuration for a tenant."""
        from app.core.cache import invalidate_tenant_cache

        update_data = {
            "business_name": business_data.business_name,
            "contact_email": business_data.contact_email,
            "contact_phone": business_data.contact_phone,
            "address": business_data.address,
            "website": business_data.website,
            "description": business_data.description,
        }
        add_updated_timestamp(update_data)

        result = await firebase_service.update_business_config(tenant_id, update_data)

        # Invalidate cache on update
        if result:
            await invalidate_tenant_cache(tenant_id)

        return result

    async def create_agent_settings(self, tenant_id: str, agent_data: AgentSettingsCreate) -> Dict[str, Any]:
        """Create agent settings for a tenant."""
        from app.core.cache import invalidate_tenant_cache

        agent_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "service_type": agent_data.service_type,
            "agent_name": agent_data.agent_name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
        }
        add_timestamps(agent_dict)

        # Store in Firebase Firestore
        result = await firebase_service.create_agent_settings(agent_dict)

        # Invalidate cache on create
        if result:
            await invalidate_tenant_cache(tenant_id)

        return result

    async def get_agent_settings(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get agent settings for a tenant (with caching)."""
        from app.core.cache import get_cached_agent_settings, set_cached_agent_settings

        # Check cache first
        cached_settings = await get_cached_agent_settings(tenant_id)
        if cached_settings:
            return cached_settings

        # Cache miss: fetch from Firebase
        settings = await firebase_service.get_agent_settings(tenant_id)
        if settings:
            # Store in cache
            await set_cached_agent_settings(tenant_id, settings)

        return settings

    async def update_agent_settings(self, tenant_id: str, agent_data: AgentSettingsCreate) -> Optional[Dict[str, Any]]:
        """Update agent settings for a tenant."""
        update_data = {
            "service_type": agent_data.service_type,
            "agent_name": agent_data.agent_name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
        }
        add_updated_timestamp(update_data)

        result = await firebase_service.update_agent_settings(tenant_id, update_data)

        # Invalidate cache on update
        if result:
            from app.core.cache import invalidate_tenant_cache

            await invalidate_tenant_cache(tenant_id)

        return result

    async def create_twilio_integration(self, tenant_id: str, twilio_data: TwilioIntegrationCreate) -> Dict[str, Any]:
        """Create Twilio integration for a tenant."""
        twilio_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "phone_number": twilio_data.phone_number,
            "webhook_url": twilio_data.webhook_url,
            "status": "active",
        }
        add_timestamps(twilio_dict)

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
        }
        add_updated_timestamp(update_data)

        return await firebase_service.update_twilio_integration(tenant_id, update_data)

    def get_prompt_for_service_type(self, service_type: str) -> str:
        """Get the appropriate prompt for a service type."""
        return prompt_map.get(service_type, prompt_map["Home Services"])


# Global tenant service instance
tenant_service = TenantService()
