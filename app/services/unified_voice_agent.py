"""
Unified LiveKit Voice Agent Service
====================================
Handles Twilio inbound phone call integration for the LiveKit worker.

ARCHITECTURE (LiveKit Official Telephony Flow):
===============================================
INBOUND CALL FLOW:
1. Twilio PSTN â†’ Backend webhook (/twilio/webhook)
2. Backend identifies tenant from called phone number (To)
3. Backend generates unique call_id for this call
4. Backend stores config under: call_config:<twilio_call_sid>
5. Backend returns TwiML <Dial><Sip> to LiveKit SIP domain
   - Passes tenant_id and call_id via SIP headers
   - Does NOT specify room name (LiveKit creates it)
6. LiveKit SIP inbound trunk receives INVITE
7. SIP Dispatch Rule creates auto-named room: call-+14438600638_x9fhA2Lt
8. Dispatch Rule launches voice-agent worker
9. Worker extracts tenant_id + call_id from SIP headers
10. Worker loads config from Redis: call_config:<twilio_call_sid>
11. Worker handles call with tenant-specific configuration

KEY PRINCIPLES:
- Backend NEVER creates LiveKit rooms for inbound calls
- Backend NEVER depends on or generates room names
- Backend stores config keyed by Twilio CallSid (NOT room name)
- Multiple tenants CAN share the same PSTN number
- Each call gets isolated config via unique call_id
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from twilio.twiml.voice_response import Dial, VoiceResponse

from app.core.async_redis import async_redis_client
from app.core.config import (
    CALL_CONFIG_TTL_SECONDS,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_SIP_DOMAIN,
    LIVEKIT_URL,
)
from app.core.utils import get_current_timestamp
from app.services.store import store
from app.utils.phone_number import normalize_phone_number_safe

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedVoiceAgentService:
    """
    Unified voice agent service for phone calls (Twilio SIP -> LiveKit bridge).

    IMPORTANT: For inbound phone calls, this service:
    - Does NOT create LiveKit rooms (dispatch rule creates them)
    - Does NOT depend on room names for config
    - Stores config by Twilio CallSid for the worker to retrieve
    """

    def __init__(self):
        """Initialize unified voice agent service."""
        self.active_sessions = {}  # session_id -> session_data (for tracking)
        self._session_ttl_seconds = max(CALL_CONFIG_TTL_SECONDS, 24 * 60 * 60)

        # Validate LiveKit configuration at startup
        self._validate_livekit_config()

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"voice_session:{session_id}"

    @staticmethod
    def _tenant_session_set_key(tenant_id: str) -> str:
        return f"voice_tenant_sessions:{tenant_id}"

    @staticmethod
    def _callsid_session_key(twilio_call_sid: str) -> str:
        return f"voice_callsid_session:{twilio_call_sid}"

    async def _store_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Store session in Redis (authoritative) and mirror in memory as cache."""
        await async_redis_client.set_json(self._session_key(session_id), session_data, ttl=self._session_ttl_seconds)
        tenant_id = session_data.get("tenant_id")
        if tenant_id:
            tenant_set = self._tenant_session_set_key(str(tenant_id))
            await async_redis_client.sadd(tenant_set, session_id)
            await async_redis_client.expire(tenant_set, self._session_ttl_seconds)
        twilio_call_sid = session_data.get("twilio_call_sid")
        if twilio_call_sid:
            await async_redis_client.set(
                self._callsid_session_key(str(twilio_call_sid)), session_id, ttl=self._session_ttl_seconds
            )
        self.active_sessions[session_id] = session_data

    async def _get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session from Redis first, fallback to memory cache."""
        data = await async_redis_client.get_json(self._session_key(session_id))
        if data:
            self.active_sessions[session_id] = data
            return data
        return self.active_sessions.get(session_id)

    async def _update_session(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Patch and persist a session."""
        existing = await self._get_session(session_id)
        if not existing:
            return None
        merged = {**existing, **updates}
        await self._store_session(session_id, merged)
        return merged

    async def _find_session_by_twilio_call_sid(self, call_sid: Optional[str]) -> Optional[Dict[str, Any]]:
        if not call_sid:
            return None
        mapped_session_id = await async_redis_client.get(self._callsid_session_key(call_sid))
        if mapped_session_id:
            return await self._get_session(mapped_session_id)
        for _, sess_data in self.active_sessions.items():
            if sess_data.get("twilio_call_sid") == call_sid:
                return sess_data
        return None

    def _validate_livekit_config(self):
        """Validate LiveKit configuration at startup."""
        logger.info("=" * 60)
        logger.info("VALIDATING LIVEKIT CONFIGURATION")
        logger.info("=" * 60)
        logger.info(f"LIVEKIT_URL: '{LIVEKIT_URL}'")
        logger.info(f"LIVEKIT_API_KEY: {'âœ“ SET' if LIVEKIT_API_KEY else 'âœ— NOT SET'}")
        logger.info(f"LIVEKIT_API_SECRET: {'âœ“ SET' if LIVEKIT_API_SECRET else 'âœ— NOT SET'}")
        logger.info(f"LIVEKIT_SIP_DOMAIN: '{LIVEKIT_SIP_DOMAIN}'")

        if not LIVEKIT_URL or LIVEKIT_URL.strip() == "":
            logger.error("âš ï¸ CRITICAL: LIVEKIT_URL is not configured!")
            logger.error("Please set LIVEKIT_URL in your .env file")
        else:
            logger.info("âœ“ LIVEKIT_URL is configured")

        if not LIVEKIT_SIP_DOMAIN or LIVEKIT_SIP_DOMAIN.strip() == "":
            logger.error("âš ï¸ CRITICAL: LIVEKIT_SIP_DOMAIN is not configured!")
            logger.error("Please set LIVEKIT_SIP_DOMAIN in your .env file")
        else:
            logger.info("âœ“ LIVEKIT_SIP_DOMAIN is configured")

        logger.info("=" * 60)

    def _resolve_agent_type(agent_data: Optional[Dict[str, Any]]) -> str:
        """Resolve agent type with migration fallback."""
        if not agent_data:
            return "voice"
        return agent_data.get("agent_type") or "voice"

    async def handle_twilio_webhook(self, form_data: Dict[str, Any]) -> VoiceResponse:
        """
        Handle incoming Twilio webhook for INBOUND calls.
        
        CANONICAL FLOW:
        1. Extract call information from Twilio
        2. Lookup agent by phone number (To)
        3. Generate unique call_id for this call
        4. Store config under tenant_config:<tenant_id>:<call_id>
        5. Return TwiML that dials LiveKit SIP domain
           - Pass tenant_id and call_id via SIP headers
           - Do NOT specify room name (LiveKit creates it)
        
        IMPORTANT: We do NOT create LiveKit rooms here.
        The SIP dispatch rule creates the room automatically.
        """
        try:
            # Extract call information
            call_sid = form_data.get("CallSid")
            from_number = form_data.get("From")
            to_number = form_data.get("To")

            logger.info(f"[TWILIO WEBHOOK] Inbound call: CallSid={call_sid}, From={from_number}, To={to_number}")

            # ========================================
            # INBOUND CALL HANDLING (NEW ARCHITECTURE)
            # ========================================
            logger.info(f"[TWILIO WEBHOOK] Processing as INBOUND call to {to_number}")

            # Step 1: Normalize phone number
            normalized_to_number = normalize_phone_number_safe(to_number)
            if not normalized_to_number:
                logger.error(f"[TWILIO WEBHOOK] Invalid phone number format: {to_number}")
                return self._error_response("Invalid phone number format. Please contact support.")

            logger.info(f"[TWILIO WEBHOOK] Normalized phone number: {to_number} -> {normalized_to_number}")

            # Step 2: Lookup phone number assignment
            phone_record = await store.get_phone_by_number(normalized_to_number)
            if not phone_record:
                phone_record = await store.get_phone_by_number(to_number)

            if not phone_record:
                logger.error(f"[TWILIO WEBHOOK] Phone number {normalized_to_number} not found in database")
                return self._error_response("This number is not configured. Please contact support.")

            logger.info(f"[TWILIO WEBHOOK] âœ“ Found phone record: ID={phone_record.get('id')}, AgentID={phone_record.get('agent_id')}")

            # Step 3: Validate phone record has required fields
            agent_id = phone_record.get("agent_id")
            tenant_id = phone_record.get("tenant_id")

            if not agent_id:
                logger.error("[TWILIO WEBHOOK] Phone number has no agent_id assigned")
                return self._error_response("This number is not assigned to an agent. Please contact support.")

            if not tenant_id:
                logger.error("[TWILIO WEBHOOK] Phone number has no tenant_id")
                return self._error_response("Configuration error. Please contact support.")

            # Step 4: Get agent configuration
            agent = await store.get_agent(agent_id)
            if not agent:
                logger.error(f"[TWILIO WEBHOOK] Agent {agent_id} not found")
                return self._error_response("Agent configuration not found. Please contact support.")

            logger.info(f"[TWILIO WEBHOOK] âœ“ Found agent: Name={agent.get('name')}, ServiceType={agent.get('service_type')}")

            # Voice safety: inbound phone calls can only target voice agents.
            # Legacy agents without an explicit type are treated as voice.
            agent_type = self._resolve_agent_type(agent)
            if agent_type != "voice":
                logger.error(f"[TWILIO WEBHOOK] Agent {agent_id} has type={agent_type} - FAILING CALL")
                return self._error_response("This number is assigned to a non-voice agent. Please contact support.")

            # Step 5: Validate agent has service_type (NO FALLBACK)
            service_type = agent.get("service_type")
            if not service_type:
                logger.error(f"[TWILIO WEBHOOK] Agent {agent_id} has no service_type - FAILING CALL")
                return self._error_response("Agent configuration is incomplete. Please contact support.")

            # Step 6: Generate unique call_id for this call
            call_id = str(uuid.uuid4())[:12]
            logger.info(f"[TWILIO WEBHOOK] Generated call_id: {call_id}")

            # Step 7: Prepare tenant config for worker
            config_data = {
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "call_id": call_id,
                "agent_data": self._clean_agent_data(agent),
                "voice_id": agent.get("voice_id"),
                "agent_type": agent_type,
                "service_type": service_type,
                "call_type": "inbound",
                "caller_number": from_number,
                "called_number": normalized_to_number,
                "twilio_call_sid": call_sid,
                "created_at": get_current_timestamp(),
            }

            # Step 8: Store config in Redis for worker to retrieve
            # IMPORTANT: Store by TWILIO CALL SID because that's what the worker can reliably read
            # from sip.twilio.callSid attribute (custom SIP headers via query params don't work)
            await self._store_config_by_twilio_callsid(call_sid, config_data)
            
            # Also store by tenant+call_id for backward compatibility and cleanup
            stored = await self._store_tenant_config(tenant_id, call_id, config_data)
            if not stored:
                logger.error("[TWILIO WEBHOOK] Failed to store tenant config")
                return self._error_response("Unable to initialize call. Please try again later.")

            logger.info(f"[TWILIO WEBHOOK] âœ“ Stored config: call_config:{call_sid}")

            # Step 9 & 10: Build SIP URI WITH original Twilio CallSid
            # CRITICAL: Twilio creates a NEW CallSid when dialing LiveKit via SIP
            # We must pass our original CallSid as x-lk-callid query param
            sip_uri = self._build_sip_uri_with_callsid(call_sid, tenant_id, normalized_to_number)
            
            logger.info(f"[TWILIO WEBHOOK] Complete SIP URI: {sip_uri}")

            # Step 11: Build TwiML response
            response = VoiceResponse()
            dial = Dial()
            dial.sip(sip_uri)
            response.append(dial)

            # Step 12: Track session for status callbacks (Redis-backed store)
            session_id = f"inbound-{call_sid}"
            await self._store_session(
                session_id,
                {
                "session_id": session_id,
                "room_name": None,  # Room is created by LiveKit, not us
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "call_id": call_id,
                "twilio_call_sid": call_sid,
                "status": "connecting",
                "call_type": "inbound",
                "from_number": from_number,
                "to_number": to_number,
                "created_at": get_current_timestamp(),
                "started_at": get_current_timestamp(),
                },
            )

            logger.info(f"[TWILIO WEBHOOK] âœ“ Inbound call setup complete: tenant={tenant_id}, agent={agent.get('name')}")
            return response

        except Exception as e:
            logger.error(f"[TWILIO WEBHOOK] Error: {e}", exc_info=True)
            return self._error_response("An error occurred. Please try again later.")

    async def handle_twilio_status_callback(self, form_data: Dict[str, Any]):
        """Handle Twilio call status updates."""
        try:
            call_sid = form_data.get("CallSid")
            call_status = form_data.get("CallStatus")

            logger.info(f"[TWILIO STATUS] CallSid={call_sid}, Status={call_status}")

            session = await self._find_session_by_twilio_call_sid(call_sid)
            if not session:
                return

            session_id = session.get("session_id")
            if not session_id:
                return

            updates: Dict[str, Any] = {"twilio_status": call_status}
            if call_status in ["completed", "failed", "busy", "no-answer"]:
                updates["status"] = "ended"
                updates["ended_at"] = get_current_timestamp()

            updated = await self._update_session(session_id, updates)
            if not updated:
                return

            if call_status in ["completed", "failed", "busy", "no-answer"]:
                # Cleanup: Delete configs from Redis
                tenant_id = updated.get("tenant_id")
                call_id = updated.get("call_id")
                twilio_call_sid = updated.get("twilio_call_sid")

                # Delete call_config (primary lookup key by Twilio CallSid)
                if twilio_call_sid:
                    try:
                        call_config_key = f"call_config:{twilio_call_sid}"
                        await async_redis_client.delete(call_config_key)
                        logger.info(f"[CLEANUP] Deleted config: {call_config_key}")
                    except Exception as e:
                        logger.warning(f"[CLEANUP] Failed to delete call_config: {e}")

                # Delete tenant_config (backup key)
                if tenant_id and call_id:
                    try:
                        tenant_config_key = f"tenant_config:{tenant_id}:{call_id}"
                        await async_redis_client.delete(tenant_config_key)
                        logger.info(f"[CLEANUP] Deleted config: {tenant_config_key}")
                    except Exception as e:
                        logger.warning(f"[CLEANUP] Failed to delete tenant_config: {e}")

        except Exception as e:
            logger.error(f"[TWILIO STATUS] Error: {e}")

    # ========================================
    # PRIVATE HELPER METHODS
    # ========================================

    def _error_response(self, message: str) -> VoiceResponse:
        """Create an error TwiML response."""
        response = VoiceResponse()
        response.say(message)
        response.hangup()
        return response

    def _clean_agent_data(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean agent data for JSON serialization."""
        if not agent_data:
            return None
        return {
            "id": agent_data.get("id"),
            "agent_type": self._resolve_agent_type(agent_data),
            "name": agent_data.get("name"),
            "voice_id": agent_data.get("voice_id"),
            "language": agent_data.get("language"),
            "greeting_message": agent_data.get("greeting_message"),
            "service_type": agent_data.get("service_type"),
            "tenant_id": agent_data.get("tenant_id"),
        }

    async def _store_tenant_config(
        self, tenant_id: str, call_id: str, config: Dict[str, Any], ttl: int = CALL_CONFIG_TTL_SECONDS
    ) -> bool:
        """
        Store tenant configuration in Redis for worker to retrieve.
        
        Key format: tenant_config:<tenant_id>:<call_id>
        
        This approach:
        - Supports multiple tenants sharing the same phone number
        - Provides per-call isolation via call_id
        - Does NOT depend on room name
        """
        try:
            config_key = f"tenant_config:{tenant_id}:{call_id}"
            config_json = json.dumps(config)
            
            logger.info(f"[REDIS STORE] Storing config with key: {config_key}")
            await async_redis_client.set(config_key, config_json, ttl=ttl)
            
            # Verify storage
            verify_data = await async_redis_client.get(config_key)
            if verify_data:
                logger.info("[REDIS STORE] âœ“ Successfully stored and verified config")
                return True
            else:
                logger.error("[REDIS STORE] âœ— Failed to verify config storage")
                return False
                
        except Exception as exc:
            logger.error(f"[REDIS STORE] âœ— Error storing config: {exc}", exc_info=True)
            return False

    async def _store_config_by_twilio_callsid(
        self, twilio_call_sid: str, config: Dict[str, Any], ttl: int = CALL_CONFIG_TTL_SECONDS
    ) -> bool:
        """
        Store call configuration in Redis by Twilio CallSid.
        
        Key format: call_config:<twilio_call_sid>
        
        This is the PRIMARY lookup method for the worker because:
        - sip.twilio.callSid is ALWAYS available in SIP participant attributes
        - Custom SIP headers via query params are NOT forwarded by Twilio to LiveKit
        
        The worker will use this key to retrieve the full config including tenant_id.
        """
        try:
            config_key = f"call_config:{twilio_call_sid}"
            config_json = json.dumps(config)
            
            logger.info(f"[REDIS STORE] Storing config by Twilio CallSid: {config_key}")
            await async_redis_client.set(config_key, config_json, ttl=ttl)
            
            # Verify storage
            verify_data = await async_redis_client.get(config_key)
            if verify_data:
                logger.info("[REDIS STORE] âœ“ Successfully stored config by Twilio CallSid")
                return True
            else:
                logger.error("[REDIS STORE] âœ— Failed to verify config storage by Twilio CallSid")
                return False
                
        except Exception as exc:
            logger.error(f"[REDIS STORE] âœ— Error storing config by Twilio CallSid: {exc}", exc_info=True)
            return False

    def _build_sip_uri_with_callsid(self, twilio_call_sid: str, tenant_id: str, called_number: str) -> str:
        """
        Build SIP URI with the original Twilio CallSid as query parameter.
        
        CRITICAL: Twilio creates a NEW CallSid when it dials LiveKit via SIP.
        So sip.twilio.callSid in the worker is DIFFERENT from the webhook CallSid!
        
        We must pass our original CallSid via x-lk-callid query param so the worker
        can read it from sip.h.x-lk-callid and match it with Redis.
        
        Format: sip:lk@domain?x-lk-callid=CA123&x-lk-tenantid=...&x-lk-callednumber=...
        
        LiveKit will expose these as participant attributes:
        - sip.h.x-lk-callid
        - sip.h.x-lk-tenantid
        - sip.h.x-lk-callednumber
        """
        from urllib.parse import urlencode
        
        domain = self._get_livekit_sip_domain()
        
        # Build query parameters with our metadata
        # These become X-LK-* SIP headers that are mapped via headers_to_attributes
        query_params = urlencode({
            "X-LK-CallId": twilio_call_sid,
            "X-LK-TenantId": tenant_id,
            "X-LK-CalledNumber": called_number,
        })
        
        sip_uri = f"sip:lk@{domain}?{query_params}"
        
        logger.info(f"[SIP URI] Built URI with CallSid: {sip_uri}")
        logger.info(f"[SIP URI] Included metadata: callid={twilio_call_sid}, tenant={tenant_id}, number={called_number}")
        return sip_uri

    def _get_livekit_sip_domain(self) -> str:
        """
        Get the cleaned LiveKit SIP domain.
        
        Returns just the domain without sip: prefix.
        """
        if not LIVEKIT_SIP_DOMAIN:
            raise ValueError("LIVEKIT_SIP_DOMAIN is not configured")
        
        domain = LIVEKIT_SIP_DOMAIN.strip()
        if domain.startswith("sip:"):
            domain = domain[4:].strip()
        
        return domain

# Global instance
unified_voice_agent_service = UnifiedVoiceAgentService()
