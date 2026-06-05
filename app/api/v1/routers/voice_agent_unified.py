"""
Unified Voice Agent API Router
Handles Twilio phone call webhooks for the Gemini Live voice worker.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app.core import config
from app.core.encryption import encryption_service
from app.core.security import SecurityService
from app.services.store import store
from app.services.unified_voice_agent import unified_voice_agent_service

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-agent", tags=["Voice Agent"])

def get_security_service() -> SecurityService:
    """Get security service instance."""
    try:
        return SecurityService()
    except Exception as e:
        logger.warning(f"Security service unavailable: {e}")
        return None

def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"

# API Endpoints


async def _validate_twilio_signature(request: Request, form_data: Dict[str, Any]) -> bool:
    """
    Validate Twilio webhook signature to ensure request is from Twilio.

    Returns True if signature is valid, False otherwise.
    """
    try:
        signature = request.headers.get("X-Twilio-Signature")
        if not signature:
            logger.warning("Missing X-Twilio-Signature header in webhook request")
            return False

        account_sid = form_data.get("AccountSid")
        if not account_sid:
            logger.warning("Missing AccountSid in webhook request")
            return False

        auth_token = None

        try:
            to_number = form_data.get("To")
            if to_number:
                phone_record = await store.get_phone_by_number(to_number)
                if phone_record and phone_record.get("tenant_id"):
                    integration = await store.get_twilio_integration(phone_record["tenant_id"])
                    if integration and integration.get("account_sid") == account_sid:
                        encrypted_token = integration.get("auth_token")
                        if encrypted_token:
                            auth_token = encryption_service.decrypt(encrypted_token)
        except Exception as e:
            logger.warning(f"Could not get auth_token from integration: {e}")

        if not auth_token:
            if config.TWILIO_ACCOUNT_SID == account_sid and config.TWILIO_AUTH_TOKEN:
                auth_token = config.TWILIO_AUTH_TOKEN
                logger.info("Using system Twilio credentials for signature validation")

        if not auth_token:
            logger.error(f"Could not find auth_token for AccountSid: {account_sid}")
            return False

        url = str(request.url)
        if "?" in url:
            url = url.split("?")[0]

        params = {k: str(v) for k, v in form_data.items()}
        is_valid = RequestValidator(auth_token).validate(url, params, signature)

        if not is_valid:
            logger.warning(f"Invalid Twilio signature for AccountSid: {account_sid}")

        return is_valid

    except Exception as e:
        logger.error(f"Error validating Twilio signature: {e}", exc_info=True)
        return False

@router.post("/twilio/webhook")
async def twilio_webhook(request: Request):
    """
    Twilio webhook endpoint.

    This is called by Twilio when a call is initiated.
    Returns TwiML that connects the call to LiveKit room via SIP.

    Security: Validates X-Twilio-Signature header to ensure request is from Twilio.
    """
    # Rate limiting: 100 requests per minute per IP (higher for legitimate webhook traffic)
    security_service = get_security_service()
    if security_service:
        client_ip = get_client_ip(request)
        await security_service.enforce_rate_limit(client_ip, limit=100, window_seconds=60, operation="twilio_webhook")

    try:
        form_data = await request.form()
        form_dict = dict(form_data)

        # Validate Twilio signature for security
        if not await _validate_twilio_signature(request, form_dict):
            logger.error("Invalid Twilio signature - rejecting webhook request")
            # Return error TwiML instead of HTTP error (Twilio expects TwiML)
            from twilio.twiml.voice_response import VoiceResponse

            error_response = VoiceResponse()
            error_response.say("Authentication error. Please contact support.")
            error_response.hangup()
            return Response(content=str(error_response), media_type="application/xml", status_code=403)

        logger.info("Twilio signature validated successfully")

        response = await unified_voice_agent_service.handle_twilio_webhook(form_dict)

        return Response(content=str(response), media_type="application/xml")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Twilio webhook: {e}", exc_info=True)
        # Return error TwiML
        from twilio.twiml.voice_response import VoiceResponse

        error_response = VoiceResponse()
        error_response.say("An application error occurred. Please try again later.")
        error_response.hangup()
        return Response(content=str(error_response), media_type="application/xml")

@router.post("/twilio/status")
async def twilio_status_callback(request: Request):
    """
    Twilio status callback endpoint.

    This is called by Twilio to report call status changes.

    Security: Validates X-Twilio-Signature header to ensure request is from Twilio.
    """
    # Rate limiting: 100 requests per minute per IP (higher for legitimate webhook traffic)
    security_service = get_security_service()
    if security_service:
        client_ip = get_client_ip(request)
        await security_service.enforce_rate_limit(client_ip, limit=100, window_seconds=60, operation="twilio_status")

    try:
        form_data = await request.form()
        form_dict = dict(form_data)

        # Validate Twilio signature for security
        if not await _validate_twilio_signature(request, form_dict):
            logger.error("Invalid Twilio signature - rejecting status callback request")
            return Response(status_code=403, content="Invalid signature")

        logger.info("Twilio signature validated successfully for status callback")

        await unified_voice_agent_service.handle_twilio_status_callback(form_dict)

        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Error in Twilio status callback: {e}", exc_info=True)
        return Response(status_code=500)
