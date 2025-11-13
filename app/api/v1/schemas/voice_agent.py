"""
Pydantic schemas for voice agent operations.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class VoiceCallStart(BaseModel):
    """Schema for starting a voice call."""

    tenant_id: str = Field(..., description="Tenant ID")
    service_type: str = Field(default="Home Services", description="Type of service")
    test_mode: bool = Field(default=True, description="Whether to use test mode")
    phone_number: Optional[str] = Field(None, description="Phone number for live calls")
    call_source: str = Field(default="dashboard", description="Source of the call")


class VoiceCallResponse(BaseModel):
    """Schema for voice call response."""

    call_id: str = Field(..., description="Unique call ID")
    status: str = Field(..., description="Call status")
    session_data: Dict[str, Any] = Field(..., description="Session data")
    test_mode: bool = Field(..., description="Whether in test mode")


class CallStatus(BaseModel):
    """Schema for call status."""

    call_id: str = Field(..., description="Call ID")
    status: str = Field(..., description="Current status")
    started_at: str = Field(..., description="Call start time")
    ended_at: Optional[str] = Field(None, description="Call end time")
    duration_seconds: Optional[int] = Field(None, description="Call duration")
    service_type: str = Field(..., description="Service type")
    test_mode: bool = Field(..., description="Test mode flag")


class CallHistory(BaseModel):
    """Schema for call history."""

    calls: List[CallStatus] = Field(..., description="List of calls")
    total: int = Field(..., description="Total number of calls")
    limit: int = Field(..., description="Limit per page")
    offset: int = Field(..., description="Offset for pagination")


class VoiceAgentConfig(BaseModel):
    """Schema for voice agent configuration."""

    voice_id: str = Field(default="en_us_006", description="Voice ID for TTS")
    language: str = Field(default="en-US", description="Language code")
    greeting_message: str = Field(..., description="Greeting message")
    service_type: str = Field(..., description="Service type")
    escalation_phone: Optional[str] = Field(None, description="Escalation phone number")
    max_confirmation_attempts: int = Field(default=3, description="Max confirmation attempts")
    call_timeout_seconds: int = Field(default=300, description="Call timeout in seconds")


class TwilioWebhookData(BaseModel):
    """Schema for Twilio webhook data."""

    CallSid: str = Field(..., description="Twilio Call SID")
    From: str = Field(..., description="Caller phone number")
    To: str = Field(..., description="Called phone number")
    CallStatus: str = Field(..., description="Call status")
    Direction: str = Field(..., description="Call direction")
    ForwardedFrom: Optional[str] = Field(None, description="Forwarded from number")


class TwilioStatusCallback(BaseModel):
    """Schema for Twilio status callback."""

    CallSid: str = Field(..., description="Twilio Call SID")
    CallStatus: str = Field(..., description="Call status")
    CallDuration: Optional[str] = Field(None, description="Call duration")
    Direction: str = Field(..., description="Call direction")


class VoiceAgentMetrics(BaseModel):
    """Schema for voice agent metrics."""

    total_calls: int = Field(..., description="Total calls")
    successful_calls: int = Field(..., description="Successful calls")
    failed_calls: int = Field(..., description="Failed calls")
    average_duration: float = Field(..., description="Average call duration")
    conversion_rate: float = Field(..., description="Appointment conversion rate")
    escalation_rate: float = Field(..., description="Escalation rate")


class TwilioIntegrationConfig(BaseModel):
    """Schema for Twilio integration configuration."""

    account_sid: str = Field(..., description="Twilio Account SID")
    auth_token: str = Field(..., description="Twilio Auth Token")
    phone_number: Optional[str] = Field(None, description="Twilio phone number (optional for initial setup)")
    webhook_url: Optional[str] = Field(
        None, description="Webhook URL (optional, uses TWILIO_WEBHOOK_BASE_URL if not provided)"
    )
    status_callback_url: Optional[str] = Field(
        None, description="Status callback URL (optional, uses TWILIO_WEBHOOK_BASE_URL if not provided)"
    )
    verify_credentials: bool = Field(default=True, description="Verify credentials")


class TwilioCredentialTest(BaseModel):
    """Schema for testing Twilio credentials."""

    account_sid: str = Field(..., description="Twilio Account SID")
    auth_token: str = Field(..., description="Twilio Auth Token")
    phone_number: Optional[str] = Field(None, description="Phone number to test (optional for basic credential verification)")


class TwilioCredentialTestResponse(BaseModel):
    """Schema for Twilio credential test response."""

    success: bool = Field(..., description="Test success status")
    message: str = Field(..., description="Test result message")
    phone_number: Optional[str] = Field(None, description="Verified phone number")
    account_info: Optional[Dict[str, Any]] = Field(None, description="Account information")
    is_test_account: bool = Field(default=False, description="Whether these are test account credentials")
