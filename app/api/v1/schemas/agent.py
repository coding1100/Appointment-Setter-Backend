"""
Agent schemas for API requests and responses.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator

from app.core.validators import validate_service_type


class AgentCreate(BaseModel):
    """Schema for creating a new agent."""

    name: str = Field(..., min_length=1, max_length=100, description="Agent name (e.g., 'Receptionist Sarah')")
    voice_id: str = Field(..., description="ElevenLabs voice ID")
    language: str = Field(default="en-US", description="Language code (e.g., en-US, es-ES)")
    greeting_message: str = Field(..., min_length=10, max_length=1000, description="Agent greeting message")
    service_type: str = Field(..., description="Service type")

    @validator("service_type")
    def validate_service_type(cls, v):
        """Validate service type."""
        return validate_service_type(v)


class AgentUpdate(BaseModel):
    """Schema for updating an agent."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    voice_id: Optional[str] = None
    language: Optional[str] = None
    greeting_message: Optional[str] = Field(None, min_length=10, max_length=1000)
    service_type: Optional[str] = None
    status: Optional[str] = None

    @validator("service_type")
    def validate_service_type(cls, v):
        """Validate service type."""
        if v is None:
            return v
        return validate_service_type(v)


class AgentResponse(BaseModel):
    """Schema for agent response."""

    id: str
    tenant_id: str
    name: str
    voice_id: str
    language: str
    greeting_message: str
    service_type: str
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VoiceOption(BaseModel):
    """Schema for ElevenLabs voice option."""

    voice_id: str
    name: str
    description: str
    preview_url: Optional[str] = None
    category: str  # male, female, neutral
    use_case: str  # conversational, narration, customer_service


class VoiceListResponse(BaseModel):
    """Schema for list of available voices."""

    voices: list[VoiceOption]
    total: int


class VoicePreviewRequest(BaseModel):
    """Schema for voice preview request."""

    voice_id: str
    text: Optional[str] = Field(
        default="Hello! This is a preview of my voice. I'm here to help you schedule appointments and answer your questions.",
        max_length=500,
    )
