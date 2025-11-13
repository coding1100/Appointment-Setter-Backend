"""
Phone number schemas for linking agents with Twilio integrations.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, validator
from uuid import UUID


class PhoneNumberCreate(BaseModel):
    """Schema for creating a phone number assignment."""
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$', description="Phone number in E.164 format")
    agent_id: str = Field(..., description="Agent ID to assign this phone number to")
    twilio_integration_id: str = Field(..., description="Twilio integration ID")
    
    @validator('phone_number')
    def validate_phone_format(cls, v):
        """Ensure phone number is in E.164 format."""
        if not v.startswith('+'):
            raise ValueError('Phone number must start with + and country code (E.164 format)')
        return v


class PhoneNumberUpdate(BaseModel):
    """Schema for updating a phone number assignment."""
    phone_number: Optional[str] = Field(None, pattern=r'^\+?[1-9]\d{1,14}$')
    agent_id: Optional[str] = None
    status: Optional[str] = None
    
    @validator('phone_number')
    def validate_phone_format(cls, v):
        """Ensure phone number is in E.164 format."""
        if v is not None and not v.startswith('+'):
            raise ValueError('Phone number must start with + and country code (E.164 format)')
        return v


class PhoneNumberResponse(BaseModel):
    """Schema for phone number response."""
    id: str
    tenant_id: str
    phone_number: str
    agent_id: str
    agent_name: Optional[str] = None  # Populated from agent data
    twilio_integration_id: str
    status: str  # active, inactive
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class AgentPhoneAssignment(BaseModel):
    """Schema for assigning phone number to agent."""
    agent_id: str = Field(..., description="Agent ID")
    phone_number: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$', description="Phone number in E.164 format")
    
    @validator('phone_number')
    def validate_phone_format(cls, v):
        """Ensure phone number is in E.164 format."""
        if not v.startswith('+'):
            raise ValueError('Phone number must start with + and country code (E.164 format)')
        return v

