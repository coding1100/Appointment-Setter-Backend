"""
Phone number service layer for business logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.v1.schemas.phone_number import PhoneNumberCreate, PhoneNumberUpdate
from app.services.firebase import firebase_service
from app.utils.phone_number import normalize_phone_number, normalize_phone_number_safe


class PhoneNumberService:
    """Service class for phone number operations."""

    def __init__(self):
        """Initialize phone number service."""
        pass

    async def create_phone_number(self, tenant_id: str, phone_data: PhoneNumberCreate) -> Dict[str, Any]:
        """Create a new phone number assignment."""
        # Normalize phone number to E.164 format for consistent storage
        normalized_phone = normalize_phone_number(phone_data.phone_number)

        # Check if phone number is already used (try normalized first, then original)
        existing_phone = await self.get_phone_by_number(normalized_phone)
        if not existing_phone:
            existing_phone = await self.get_phone_by_number(phone_data.phone_number)

        if existing_phone:
            raise ValueError(f"Phone number {normalized_phone} is already assigned")

        # Verify agent exists and belongs to tenant
        agent = await firebase_service.get_agent(phone_data.agent_id)
        if not agent:
            raise ValueError(f"Agent {phone_data.agent_id} not found")
        if agent.get("tenant_id") != tenant_id:
            raise ValueError(f"Agent {phone_data.agent_id} does not belong to this tenant")

        # Verify agent has service_type set (required field)
        if not agent.get("service_type"):
            raise ValueError(
                f"Agent {phone_data.agent_id} (name: {agent.get('name')}) has no service_type set. "
                f"Please configure the agent's service_type before assigning a phone number."
            )

        # Verify twilio integration exists and belongs to tenant
        twilio_integration = await firebase_service.get_twilio_integration(tenant_id)
        if not twilio_integration:
            raise ValueError(f"Twilio integration not found for this tenant")

        # Store normalized phone number
        phone_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "phone_number": normalized_phone,  # Store normalized format
            "agent_id": phone_data.agent_id,
            "twilio_integration_id": phone_data.twilio_integration_id,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        return await firebase_service.create_phone_number(phone_dict)

    async def get_phone_number(self, phone_id: str) -> Optional[Dict[str, Any]]:
        """Get phone number by ID."""
        return await firebase_service.get_phone_number(phone_id)

    async def get_phone_by_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Get phone number by actual number string.
        Tries normalized format first, then original format.
        """
        # Try normalized format first (most common)
        normalized = normalize_phone_number_safe(phone_number)
        if normalized:
            phone_record = await firebase_service.get_phone_by_number(normalized)
            if phone_record:
                return phone_record

        # Fallback to original format (for backwards compatibility)
        return await firebase_service.get_phone_by_number(phone_number)

    async def get_phone_by_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get phone number assigned to an agent."""
        return await firebase_service.get_phone_by_agent(agent_id)

    async def list_phones_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all phone numbers for a tenant."""
        phones = await firebase_service.list_phones_by_tenant(tenant_id)

        # Enrich with agent names
        for phone in phones:
            if phone.get("agent_id"):
                agent = await firebase_service.get_agent(phone["agent_id"])
                if agent:
                    phone["agent_name"] = agent.get("name")

        return phones

    async def update_phone_number(self, phone_id: str, phone_data: PhoneNumberUpdate) -> Optional[Dict[str, Any]]:
        """Update phone number assignment."""
        phone = await self.get_phone_number(phone_id)
        if not phone:
            return None

        update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if phone_data.phone_number is not None:
            # Normalize phone number before checking/updating
            normalized_phone = normalize_phone_number(phone_data.phone_number)
            # Check if new phone number is already used
            existing_phone = await self.get_phone_by_number(normalized_phone)
            if existing_phone and existing_phone["id"] != phone_id:
                raise ValueError(f"Phone number {normalized_phone} is already assigned")
            update_data["phone_number"] = normalized_phone  # Store normalized format

        if phone_data.agent_id is not None:
            # Verify agent exists and belongs to same tenant
            agent = await firebase_service.get_agent(phone_data.agent_id)
            if not agent:
                raise ValueError(f"Agent {phone_data.agent_id} not found")
            if agent.get("tenant_id") != phone.get("tenant_id"):
                raise ValueError(f"Agent {phone_data.agent_id} does not belong to this tenant")
            # Verify agent has service_type set
            if not agent.get("service_type"):
                raise ValueError(
                    f"Agent {phone_data.agent_id} (name: {agent.get('name')}) has no service_type set. "
                    f"Please configure the agent's service_type before assigning a phone number."
                )
            update_data["agent_id"] = phone_data.agent_id

        if phone_data.status is not None:
            update_data["status"] = phone_data.status

        return await firebase_service.update_phone_number(phone_id, update_data)

    async def delete_phone_number(self, phone_id: str) -> bool:
        """Delete phone number assignment."""
        return await firebase_service.delete_phone_number(phone_id)

    async def assign_phone_to_agent(
        self, tenant_id: str, agent_id: str, phone_number: str, twilio_integration_id: str
    ) -> Dict[str, Any]:
        """
        Assign a phone number to an agent.
        
        Normalizes phone number to E.164 format before storing.
        """
        # Normalize phone number first
        normalized_phone = normalize_phone_number(phone_number)

        # Verify agent exists and belongs to tenant first
        agent = await firebase_service.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        if agent.get("tenant_id") != tenant_id:
            raise ValueError(f"Agent {agent_id} does not belong to tenant {tenant_id}")

        # Verify agent has service_type (required field)
        if not agent.get("service_type"):
            raise ValueError(
                f"Agent {agent_id} (name: {agent.get('name')}) has no service_type set. "
                f"Please configure the agent's service_type before assigning a phone number."
            )

        # Check if phone number already assigned (using normalized format)
        existing_phone = await self.get_phone_by_number(normalized_phone)
        if existing_phone:
            # Verify existing phone belongs to the same tenant
            if existing_phone.get("tenant_id") != tenant_id:
                raise ValueError(f"Phone number {normalized_phone} is already assigned to a different tenant")
            # Update existing assignment with normalized phone number
            phone_data = PhoneNumberUpdate(agent_id=agent_id, phone_number=normalized_phone)
            return await self.update_phone_number(existing_phone["id"], phone_data)
        else:
            # Create new assignment with normalized phone number
            phone_data = PhoneNumberCreate(
                phone_number=normalized_phone, agent_id=agent_id, twilio_integration_id=twilio_integration_id
            )
            return await self.create_phone_number(tenant_id, phone_data)

    async def unassign_phone_from_agent(self, agent_id: str) -> bool:
        """Remove phone number assignment from an agent."""
        phone = await self.get_phone_by_agent(agent_id)
        if phone:
            return await self.delete_phone_number(phone["id"])
        return False


# Global phone number service instance
phone_number_service = PhoneNumberService()
