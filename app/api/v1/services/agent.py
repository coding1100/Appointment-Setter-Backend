"""
Agent service layer for business logic.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.api.v1.schemas.agent import AgentCreate, AgentUpdate, VoiceOption
from app.services.firebase import firebase_service


class AgentService:
    """Service class for agent operations."""
    
    def __init__(self):
        """Initialize agent service."""
        pass
    
    async def create_agent(self, tenant_id: str, agent_data: AgentCreate) -> Dict[str, Any]:
        """Create a new agent for a tenant."""
        agent_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": agent_data.name,
            "voice_id": agent_data.voice_id,
            "language": agent_data.language,
            "greeting_message": agent_data.greeting_message,
            "service_type": agent_data.service_type,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await firebase_service.create_agent(agent_dict)
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        return await firebase_service.get_agent(agent_id)
    
    
    async def list_agents_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all agents for a tenant."""
        return await firebase_service.list_agents_by_tenant(tenant_id)
    
    async def update_agent(self, agent_id: str, agent_data: AgentUpdate) -> Optional[Dict[str, Any]]:
        """Update agent."""
        agent = await self.get_agent(agent_id)
        if not agent:
            return None
        
        update_data = {
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
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
        
        return await firebase_service.update_agent(agent_id, update_data)
    
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent."""
        return await firebase_service.delete_agent(agent_id)
    
    async def activate_agent(self, agent_id: str) -> bool:
        """Activate an agent."""
        update_data = {
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        result = await firebase_service.update_agent(agent_id, update_data)
        return result is not None
    
    async def deactivate_agent(self, agent_id: str) -> bool:
        """Deactivate an agent."""
        update_data = {
            "status": "inactive",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        result = await firebase_service.update_agent(agent_id, update_data)
        return result is not None
    
    def get_available_voices(self) -> List[VoiceOption]:
        """Get list of available ElevenLabs voices."""
        # Predefined list of popular ElevenLabs voices
        voices = [
            VoiceOption(
                voice_id="21m00Tcm4TlvDq8ikWAM",
                name="Rachel",
                description="Calm, natural, young adult female voice",
                category="female",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="AZnzlk1XvdvUeBnXmlld",
                name="Domi",
                description="Strong, confident, young adult female voice",
                category="female",
                use_case="conversational"
            ),
            VoiceOption(
                voice_id="EXAVITQu4vr4xnSDxMaL",
                name="Bella",
                description="Soft, warm, young adult female voice",
                category="female",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="ErXwobaYiN019PkySvjV",
                name="Antoni",
                description="Professional, well-rounded male voice",
                category="male",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="VR6AewLTigWG4xSOukaG",
                name="Arnold",
                description="Deep, authoritative male voice",
                category="male",
                use_case="conversational"
            ),
            VoiceOption(
                voice_id="pNInz6obpgDQGcFmaJgB",
                name="Adam",
                description="Deep, mature male voice",
                category="male",
                use_case="narration"
            ),
            VoiceOption(
                voice_id="yoZ06aMxZJJ28mfd3POQ",
                name="Sam",
                description="Young, dynamic male voice",
                category="male",
                use_case="conversational"
            ),
            VoiceOption(
                voice_id="IKne3meq5aSn9XLyUdCD",
                name="Charlie",
                description="Casual, natural male voice",
                category="male",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="XB0fDUnXU5powFXDhCwa",
                name="Charlotte",
                description="Clear, professional female voice",
                category="female",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="pqHfZKP75CvOlQylNhV4",
                name="Bill",
                description="Strong, trustworthy male voice",
                category="male",
                use_case="conversational"
            ),
            VoiceOption(
                voice_id="N2lVS1w4EtoT3dr4eOWO",
                name="Callum",
                description="Smooth, mature male voice",
                category="male",
                use_case="customer_service"
            ),
            VoiceOption(
                voice_id="LcfcDJNUP1GQjkzn1xUU",
                name="Emily",
                description="Warm, friendly female voice",
                category="female",
                use_case="customer_service"
            ),
        ]
        return voices


# Global agent service instance
agent_service = AgentService()

