"""Email service — Resend HTTP API as the sole transport.

Official Python SDK: https://resend.com/docs/send-with-python
REST reference:      https://resend.com/docs/api-reference/emails/send-email
Errors:              https://resend.com/docs/api-reference/errors
Domain verification: https://resend.com/docs/dashboard/domains/introduction

Required environment:
  * RESEND_API_KEY    — Resend API key with "Sending access".
  * RESEND_FROM_EMAIL — From address. Format: "noreply@yourdomain.com" or
                        "Display Name <noreply@yourdomain.com>". The domain
                        must be verified on the Resend dashboard before any
                        send is accepted (the documented exception is
                        Resend's own "onboarding@resend.dev" address, which
                        is fine for early testing).

Optional environment:
  * RESEND_REPLY_TO   — explicit reply-to (defaults to the From address).

Behaviour:
  * The Resend Python SDK is synchronous. We invoke it via
    `asyncio.to_thread(...)` so the event loop is never blocked during
    the HTTPS round-trip.
  * `_send()` raises on hard failure; the public `send_*` methods catch
    and return False so a single email hiccup never sinks a booking.
  * Every send logs a single structured line: success carries the Resend
    message id; failure carries the exception text so the operator can see
    "unverified domain", "invalid api key", etc. straight from the docs.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import resend

from app.core.config import email_settings
from app.services.email.templates import EmailTemplates

logger = logging.getLogger(__name__)

# From values that look like a placeholder from .env.example — treat as
# "not configured" so we never silently mail with "noreply@your-domain.com".
_PLACEHOLDER_FROM_FRAGMENTS = ("your-domain.com", "example.com", "yourcompany.com")


def _is_real_email_or_pair(value: str) -> bool:
    """Accept either "addr@domain" or "Display Name <addr@domain>"."""
    value = (value or "").strip()
    if "@" not in value:
        return False
    lower = value.lower()
    return not any(frag in lower for frag in _PLACEHOLDER_FROM_FRAGMENTS)


class EmailService:
    """Resend-backed email service.

    Public method signatures are unchanged from the prior implementations
    (fastapi_mail -> SendGrid -> Resend), so callers (appointment_service,
    voice worker, auth flow, tests) need no edits.
    """

    def __init__(self) -> None:
        self._api_key: str = (email_settings.RESEND_API_KEY or "").strip()
        self._from_email: str = (
            email_settings.RESEND_FROM_EMAIL.strip()
            if _is_real_email_or_pair(email_settings.RESEND_FROM_EMAIL)
            else ""
        )
        self._reply_to: Optional[str] = (
            email_settings.RESEND_REPLY_TO.strip()
            if _is_real_email_or_pair(email_settings.RESEND_REPLY_TO)
            else None
        )

        # The SDK reads its key from a module-level attribute; safe to set
        # repeatedly (idempotent) and harmless if the key is empty — the
        # send call itself will surface the auth error.
        if self._api_key:
            resend.api_key = self._api_key
            logger.info(
                "[EMAIL] transport=resend from=%s reply_to=%s",
                self._from_email or "<unset>",
                self._reply_to or self._from_email or "<unset>",
            )
        else:
            logger.error(
                "[EMAIL] RESEND_API_KEY is not configured — email sends will fail."
            )

        if not self._from_email:
            logger.error(
                "[EMAIL] RESEND_FROM_EMAIL is not configured (or looks like a "
                "placeholder). Set it to a verified Resend sender — see "
                "https://resend.com/docs/dashboard/domains/introduction"
            )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    async def _send(self, subject: str, recipients: List[str], html_body: str) -> None:
        """Send via Resend; raises on hard failure.

        Resend documents specific error codes (401 missing/restricted key,
        403 unverified domain, 422 invalid From, 429 quota/rate). The SDK
        surfaces these as exceptions which we let propagate to the caller
        after logging.
        """
        if not self._api_key:
            raise RuntimeError("RESEND_API_KEY is not configured")
        if not self._from_email:
            raise RuntimeError("RESEND_FROM_EMAIL is not configured")
        if not recipients:
            raise ValueError("send() called with no recipients")

        # Per https://resend.com/docs/api-reference/emails/send-email
        params: Dict = {
            "from": self._from_email,
            "to": list(recipients),
            "subject": subject,
            "html": html_body,
        }
        if self._reply_to:
            params["reply_to"] = self._reply_to

        try:
            # SDK is sync; offload the HTTPS round-trip to a worker thread.
            response = await asyncio.to_thread(resend.Emails.send, params)
        except Exception as exc:
            # Surface the exact provider message — for the common
            # misconfigurations Resend's docs document the failure mode
            # right there in the error text (unverified domain, invalid
            # api key, daily quota exceeded, etc.).
            logger.error(
                "[EMAIL] Resend send failed for to=%s subject=%r: %s",
                recipients, subject, exc, exc_info=True,
            )
            raise

        message_id = (response or {}).get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info(
            "[EMAIL] sent (resend) to=%s subject=%r id=%s",
            recipients, subject, message_id or "<unknown>",
        )

    # ------------------------------------------------------------------
    # Public send_* methods (signatures unchanged across transport swaps)
    # ------------------------------------------------------------------
    async def send_raw_email(self, to_email: str, subject: str, body: str) -> str:
        """Generic raw send used by the AI agent tool."""
        try:
            html = EmailTemplates.generic_submission(to_email or "AI Agent User", body, "N/A")
            await self._send(subject, [to_email], html)
            return f"Email successfully sent to {to_email}"
        except Exception as e:
            return f"Failed to send email: {str(e)}"

    async def send_appointment_confirmation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        service_type: str,
        service_address: str,
        appointment_id: Optional[str] = None,
        service_details: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type,
                "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "service_address": service_address,
                "appointment_id": appointment_id or "N/A",
                "service_details": service_details,
                "business_name": business_name or "AI Phone Scheduler",
            }
            subject, html = EmailTemplates.appointment_confirmation(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending appointment confirmation email: {e}", exc_info=True)
            return False

    async def send_appointment_owner_notification(
        self,
        owner_email: str,
        customer_name: str,
        customer_email: str,
        appointment_datetime: datetime,
        service_type: str,
        service_address: str,
        appointment_id: Optional[str] = None,
        service_details: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "customer_email": customer_email,
                "service_type": service_type,
                "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "service_address": service_address,
                "appointment_id": appointment_id or "N/A",
                "service_details": service_details,
                "business_name": business_name or "AI Phone Scheduler",
            }
            subject, html = EmailTemplates.appointment_owner_notification(data)
            await self._send(subject, [owner_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending appointment owner email: {e}", exc_info=True)
            return False

    async def send_appointment_cancellation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        reason: Optional[str] = None,
        service_type: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type or "Service",
                "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "old_status": "scheduled",
                "new_status": "cancelled",
                "appointment_id": "N/A",
                "business_name": business_name or "AI Phone Scheduler",
                "cancellation_reason": reason,
            }
            subject, html = EmailTemplates.appointment_status_update(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending appointment cancellation email: {e}", exc_info=True)
            return False

    async def send_appointment_reschedule(
        self,
        customer_email: str,
        customer_name: str,
        new_datetime: datetime,
        reason: Optional[str] = None,
        old_datetime: Optional[datetime] = None,
        service_type: Optional[str] = None,
        service_address: Optional[str] = None,
        appointment_id: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type or "Service",
                "old_datetime": old_datetime.strftime("%B %d, %Y at %I:%M %p") if old_datetime else "N/A",
                "new_datetime": new_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "service_address": service_address or "N/A",
                "appointment_id": appointment_id or "N/A",
                "business_name": business_name or "AI Phone Scheduler",
                "reschedule_reason": reason,
            }
            subject, html = EmailTemplates.appointment_reschedule(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending appointment reschedule email: {e}", exc_info=True)
            return False

    async def send_partner_owner_invite(
        self,
        *,
        owner_email: str,
        owner_name: str,
        partner_name: str,
        setup_password_url: str,
        login_url: str,
        expires_in_hours: int = 48,
        platform_name: str = "MindRind",
    ) -> bool:
        """Onboarding invite for a new partner owner."""
        try:
            subject, html = EmailTemplates.partner_owner_invite(
                {
                    "owner_name": owner_name,
                    "owner_email": owner_email,
                    "partner_name": partner_name,
                    "setup_password_url": setup_password_url,
                    "login_url": login_url,
                    "expires_in_hours": expires_in_hours,
                    "platform_name": platform_name,
                }
            )
            await self._send(subject, [owner_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending partner owner invite email: {e}", exc_info=True)
            return False

    async def send_user_setup_invite(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        workspace_name: str,
        setup_password_url: str,
        login_url: str,
        expires_in_hours: int = 48,
        platform_name: str = "MindRind",
    ) -> bool:
        """Setup invite for a newly onboarded workspace user."""
        try:
            subject, html = EmailTemplates.user_setup_invite(
                {
                    "recipient_email": recipient_email,
                    "recipient_name": recipient_name,
                    "workspace_name": workspace_name,
                    "setup_password_url": setup_password_url,
                    "login_url": login_url,
                    "expires_in_hours": expires_in_hours,
                    "platform_name": platform_name,
                }
            )
            await self._send(subject, [recipient_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending user setup invite email: {e}", exc_info=True)
            return False

    async def send_password_reset_email(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        reset_password_url: str,
        expires_in_minutes: int = 60,
        platform_name: str = "MindRind",
    ) -> bool:
        """Password reset email."""
        try:
            subject, html = EmailTemplates.password_reset(
                {
                    "recipient_email": recipient_email,
                    "recipient_name": recipient_name,
                    "reset_password_url": reset_password_url,
                    "expires_in_minutes": expires_in_minutes,
                    "platform_name": platform_name,
                }
            )
            await self._send(subject, [recipient_email], html)
            return True
        except Exception as e:
            logger.error(f"Error sending password reset email: {e}", exc_info=True)
            return False


email_service = EmailService()
