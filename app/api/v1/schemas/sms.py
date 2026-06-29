"""Pydantic schemas for the SMS App (cold-SMS outreach)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

E164_PATTERN = r"^\+?[1-9]\d{1,14}$"


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


class SmsLeadCreate(BaseModel):
    """Create/import a single cold-SMS lead."""

    phone_number: str = Field(..., pattern=E164_PATTERN, description="Lead phone number (E.164)")
    name: Optional[str] = Field(None, description="Lead display name")
    merge_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom merge values for templates")
    source: Optional[str] = Field(None, description="Where this lead came from")


class SmsLeadBulkImport(BaseModel):
    """Bulk import of leads. Deduped on (tenant, phone_number)."""

    leads: List[SmsLeadCreate] = Field(..., min_length=1, max_length=5000)


class SmsLeadResponse(BaseModel):
    id: str
    tenant_id: str
    phone_number: str
    status: str
    name: Optional[str] = None
    merge_fields: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


class SmsCampaignStep(BaseModel):
    """One step of a drip sequence."""

    body: str = Field(..., min_length=1, max_length=1600, description="Template body with {{merge}} tokens")
    delay_minutes: int = Field(0, ge=0, description="Delay after the previous step before this send")


class SmsCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    # From-number is sourced from Twilio (SMS-capable). Optional: when omitted the
    # first SMS-capable number on the account is used; when provided it is validated
    # against the account's SMS-capable numbers (never free-text trusted).
    from_phone_number: Optional[str] = Field(None, pattern=E164_PATTERN, description="An SMS-capable Twilio number")
    steps: List[SmsCampaignStep] = Field(..., min_length=1, max_length=20)
    throttle_per_min: Optional[int] = Field(None, ge=1, le=600, description="Per-tenant send rate cap")
    timezone: str = Field("UTC", description="IANA timezone for quiet-hours evaluation")
    respect_quiet_hours: bool = Field(True, description="Defer sends that land in quiet hours")
    lead_ids: List[str] = Field(default_factory=list, description="Existing leads to enroll on start")
    to_numbers: List[str] = Field(default_factory=list, description="Recipient numbers pasted directly (become leads)")


class SmsCampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    from_phone_number: Optional[str] = Field(None, pattern=E164_PATTERN)
    steps: Optional[List[SmsCampaignStep]] = Field(None, min_length=1, max_length=20)
    throttle_per_min: Optional[int] = Field(None, ge=1, le=600)
    timezone: Optional[str] = None
    respect_quiet_hours: Optional[bool] = None


class SmsCampaignResponse(BaseModel):
    id: str
    tenant_id: str
    from_phone_number: Optional[str] = None
    status: str
    name: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    throttle_per_min: Optional[int] = None
    timezone: Optional[str] = None
    respect_quiet_hours: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"


# ---------------------------------------------------------------------------
# Inbox / conversations
# ---------------------------------------------------------------------------


class SmsSendNow(BaseModel):
    """Manual one-to-one reply from the inbox (human take-over)."""

    body: str = Field(..., min_length=1, max_length=1600)


class SmsMessageResponse(BaseModel):
    id: str
    tenant_id: str
    campaign_id: Optional[str] = None
    lead_id: Optional[str] = None
    direction: str
    twilio_sid: Optional[str] = None
    status: Optional[str] = None
    from_phone_number: Optional[str] = None
    to_phone_number: Optional[str] = None
    body: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"


class SmsConversationResponse(BaseModel):
    id: str
    tenant_id: str
    lead_id: Optional[str] = None
    lead_phone_number: str
    tenant_phone_number: str
    control_mode: str
    status: str
    unread_count: int = 0
    last_message_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"


class SmsConversationDetail(SmsConversationResponse):
    messages: List[SmsMessageResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Suppressions
# ---------------------------------------------------------------------------


class SmsSuppressionCreate(BaseModel):
    phone_number: str = Field(..., pattern=E164_PATTERN)
    reason: str = Field("manual", description="opted_out | manual | bounced")

    @field_validator("reason")
    @classmethod
    def _valid_reason(cls, v: str) -> str:
        allowed = {"opted_out", "manual", "bounced"}
        if v not in allowed:
            raise ValueError(f"reason must be one of {sorted(allowed)}")
        return v


class SmsSuppressionResponse(BaseModel):
    id: str
    tenant_id: str
    phone_number: str
    reason: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"


# ---------------------------------------------------------------------------
# Twilio credentials (dedicated SMS integration) + test send
# ---------------------------------------------------------------------------


class SmsCredentials(BaseModel):
    """Twilio credentials attached explicitly within the SMS app."""

    account_sid: str = Field(..., min_length=10)
    auth_token: str = Field(..., min_length=10)


class SmsIntegrationResponse(BaseModel):
    tenant_id: Optional[str] = None
    account_sid: Optional[str] = None
    account_info: Optional[Dict[str, Any]] = None
    is_test_account: Optional[bool] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        extra = "ignore"


class SmsNumberResponse(BaseModel):
    phone_number: str
    friendly_name: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


class SmsTestSend(BaseModel):
    """Send one test SMS to a single number."""

    to: str = Field(..., pattern=E164_PATTERN, description="Recipient number (E.164)")
    body: str = Field(..., min_length=1, max_length=1600)
    from_phone_number: Optional[str] = Field(None, pattern=E164_PATTERN, description="Optional SMS-capable from-number")
