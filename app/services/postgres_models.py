"""SQLAlchemy ORM models for core platform/auth domains."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.services.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    full_name: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    allowed_app_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    default_app_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    platform_role_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    active_org_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    last_login: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrgModel(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_org_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    legacy_tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    branding: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrgMembershipModel(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_membership_org_user"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PartnerEntitlementModel(Base):
    __tablename__ = "partner_entitlements"

    partner_org_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    appointment_setter_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    onboarding_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformRoleModel(Base):
    __tablename__ = "platform_roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="platform")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    actor: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MigrationStateModel(Base):
    """Internal marker to track one-time migrations/backfills."""

    __tablename__ = "migration_state"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_lower: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BusinessConfigModel(Base):
    __tablename__ = "business_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentSettingsModel(Base):
    __tablename__ = "agent_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TwilioIntegrationModel(Base):
    __tablename__ = "twilio_integrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentDomainModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PhoneNumberModel(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AppointmentDomainModel(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    appointment_datetime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProvisioningJobModel(Base):
    __tablename__ = "provisioning_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ContactModel(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatbotAgentModel(Base):
    __tablename__ = "chatbot_agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    embed_token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatbotRuntimeLogModel(Base):
    __tablename__ = "chatbot_runtime_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chatbot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatbotChatSessionModel(Base):
    __tablename__ = "chatbot_chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chatbot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    visitor_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    origin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    control_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    assigned_operator_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    assigned_operator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatbotChatMessageModel(Base):
    __tablename__ = "chatbot_chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    sender_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
