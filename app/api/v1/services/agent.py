"""
Agent service layer for business logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.v1.schemas.agent import AgentCreate, AgentUpdate, VoiceOption
from app.services.firebase import firebase_service


class AgentService:
    """Service class for agent operations."""

    def __init__(self):
        """Initialize agent service."""
        pass

    @staticmethod
    def _ensure_voice_agent_type(agent: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Apply read-time fallback for legacy records without agent_type."""
        if not agent:
            return agent
        if not agent.get("agent_type"):
            agent = {**agent, "agent_type": "voice"}
        return agent

    async def create_agent(self, tenant_id: str, agent_data: AgentCreate) -> Dict[str, Any]:
        """Create a new agent for a tenant."""
        agent_dict = {
            "id": str(uuid.uuid4()),
            "agent_type": "voice",
            "tenant_id": tenant_id,
            "name": agent_data.name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
            "service_type": agent_data.service_type,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        created = await firebase_service.create_agent(agent_dict)
        return self._ensure_voice_agent_type(created)

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        agent = await firebase_service.get_agent(agent_id)
        return self._ensure_voice_agent_type(agent)

    async def list_agents_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all agents for a tenant."""
        agents = await firebase_service.list_agents_by_tenant(tenant_id)
        return [self._ensure_voice_agent_type(agent) for agent in agents]

    async def update_agent(self, agent_id: str, agent_data: AgentUpdate) -> Optional[Dict[str, Any]]:
        """Update agent."""
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        update_data = {"updated_at": datetime.now(timezone.utc).isoformat(), "agent_type": "voice"}

        if agent_data.name is not None:
            update_data["name"] = agent_data.name
        if agent_data.voice_id is not None:
            update_data["voice_id"] = agent_data.voice_id
        if agent_data.language is not None:
            update_data["language"] = agent_data.language
        if agent_data.greeting_message is not None:
            update_data["greeting_message"] = agent_data.greeting_message
        if agent_data.service_type is not None:
            update_data["service_type"] = agent_data.service_type
        if agent_data.status is not None:
            update_data["status"] = agent_data.status

        updated = await firebase_service.update_agent(agent_id, update_data)
        return self._ensure_voice_agent_type(updated)

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent."""
        return await firebase_service.delete_agent(agent_id)

    async def activate_agent(self, agent_id: str) -> bool:
        """Activate an agent."""
        update_data = {"status": "active", "agent_type": "voice", "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await firebase_service.update_agent(agent_id, update_data)
        return result is not None

    async def deactivate_agent(self, agent_id: str) -> bool:
        """Deactivate an agent."""
        update_data = {"status": "inactive", "agent_type": "voice", "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await firebase_service.update_agent(agent_id, update_data)
        return result is not None

    def get_available_voices(self) -> List[VoiceOption]:
        """Get list of available ElevenLabs voices."""
        from app.core.voice_metadata import get_all_voices

        # Use centralized voice metadata
        voice_metadata = get_all_voices()
        voices = [
            VoiceOption(
                voice_id=voice["voice_id"],
                name=voice["name"],
                description=voice["description"],
                category=voice["category"],
                use_case=voice["use_case"],
            )
            for voice in voice_metadata
        ]
        return voices


# Global agent service instance
agent_service = AgentService()
