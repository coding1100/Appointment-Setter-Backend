"""
LiveKit Voice Agent Worker
===========================
This worker connects to LiveKit and handles voice agent sessions for inbound telephony.

ARCHITECTURE (LiveKit Official Telephony Flow):
1. Twilio PSTN → Backend webhook
2. Backend stores tenant config under `tenant_config:<tenant_id>:<call_id>`
3. Backend returns TwiML <Dial><Sip> to LiveKit SIP domain (NO room name)
4. LiveKit SIP dispatch rule creates room automatically (e.g., call-+14438600638_x8Bg...)
5. Dispatch rule launches this worker via agent_name="voice-agent"
6. Worker extracts tenant_id + call_id from SIP participant attributes
7. Worker loads config from Redis: `tenant_config:<tenant_id>:<call_id>`
8. Worker applies tenant-specific greeting, persona, voice, etc.

KEY PRINCIPLES:
- Worker NEVER depends on room name for config lookup
- Worker MUST extract tenant_id from SIP metadata per call
- Worker MUST fail with error if tenant config is missing (NO fallback)
- Multiple tenants can share the same PSTN number (call_id provides isolation)
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    function_tool,
)
from livekit.plugins import deepgram, elevenlabs, google, silero

from app.core.async_redis import async_redis_client
from app.core.config import (
    ELEVEN_API_KEY,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    LIVEKIT_SIP_ATTRIBUTE_TENANT_ID,
    LIVEKIT_SIP_ATTRIBUTE_CALL_ID,
    LIVEKIT_SIP_ATTRIBUTE_CALLED_NUMBER,
    LIVEKIT_SIP_HEADER_TENANT_ID,
    LIVEKIT_SIP_HEADER_CALL_ID,
    LIVEKIT_SIP_HEADER_CALLED_NUMBER,
)
from app.core.prompts import get_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgentWorker")

TTS_CACHE: Dict[str, elevenlabs.TTS] = {}
DEFAULT_TTS_CACHE_KEY = "__default__"
MAX_HISTORY_LOG_LINES = 40

# VAD settings optimized for telephony
VAD_SETTINGS = {
    # Telephony audio is 8 kHz; using 8k avoids resampling overhead
    "sample_rate": 8000,
    "min_speech_duration": 0.05,     # 50ms - faster detection
    "min_silence_duration": 0.3,     # 300ms - quicker turn-taking
    "prefix_padding_duration": 0.1,  # 100ms padding
    "activation_threshold": 0.5,     # Standard threshold
}

# Global VAD cache to prevent reloading model per call
_CACHED_VAD = None


def get_cached_vad():
    """Get or create a cached VAD instance to prevent repeated model loads."""
    global _CACHED_VAD
    if _CACHED_VAD is None:
        logger.info("[VAD] Loading Silero VAD model (first time)...")
        _CACHED_VAD = silero.VAD.load(**VAD_SETTINGS)
        logger.info("[VAD] ✓ Silero VAD model loaded and cached")
    return _CACHED_VAD


def prewarm_vad(proc: Optional[agents.JobProcess] = None):
    """
    Pre-warm VAD model to prevent cold start delays.
    If a JobProcess is provided (LiveKit prewarm hook), store the VAD instance
    on proc.userdata so every session in the same worker reuses it.
    """
    try:
        logger.info("Pre-warming VAD model...")
        vad = get_cached_vad()
        if proc is not None:
            proc.userdata["vad"] = vad
        logger.info("VAD model pre-warmed successfully")
        return vad
    except Exception as e:
        logger.warning(f"Failed to pre-warm VAD model: {e}")
        return None


def get_tts_service(voice_id: Optional[str], language_code: str) -> elevenlabs.TTS:
    """Return a cached ElevenLabs TTS client to avoid expensive re-instantiation."""
    cache_key = voice_id or DEFAULT_TTS_CACHE_KEY

    cached = TTS_CACHE.get(cache_key)
    if cached:
        logger.info(f"[WORKER TTS] Reusing cached TTS instance for key={cache_key}")
        return cached

    if voice_id:
        try:
            logger.info(f"[WORKER TTS] Creating ElevenLabs TTS with custom voice_id={voice_id}...")
            tts_instance = elevenlabs.TTS(
                voice_id=voice_id, model="eleven_turbo_v2_5", language=language_code, enable_ssml_parsing=False
            )
            logger.info(
                f"[WORKER TTS] ✓ SUCCESS: Created ElevenLabs TTS with voice_id={voice_id}, language={language_code}"
            )
        except Exception as exc:
            logger.error(f"[WORKER TTS] ✗ FAILED to create TTS with voice_id {voice_id}: {exc}, using default")
            return get_tts_service(None, language_code)
    else:
        logger.info("[WORKER TTS] Using DEFAULT ElevenLabs TTS voice (no custom voice_id)")
        tts_instance = elevenlabs.TTS(api_key=ELEVEN_API_KEY)

    TTS_CACHE[cache_key] = tts_instance
    return tts_instance


class VoiceAgent(Agent):
    """Voice agent for handling customer interactions."""

    def __init__(self, instructions: str) -> None:
        super().__init__(
            tools=[],  # Add your tools here if needed
            instructions=instructions,
        )
        self._closing_task: Optional[asyncio.Task] = None

    def _on_close_task_done(self, task: asyncio.Task) -> None:
        """Ensure close task exceptions are surfaced."""
        try:
            task.result()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Error closing session: {exc}", exc_info=True)
        finally:
            self._closing_task = None

    @function_tool
    async def close_session(self):
        """Called when user wants to leave the conversation."""
        if self._closing_task and not self._closing_task.done():
            logger.info("Session close already requested, waiting for completion")
            return

        logger.info("Closing session from function tool")
        await self.session.generate_reply(instructions="say goodbye to the user")
        self._closing_task = asyncio.create_task(self.session.aclose())
        self._closing_task.add_done_callback(self._on_close_task_done)


def is_sip_participant(p) -> bool:
    """
    Determine if a participant is a SIP/PSTN caller.
    
    FIX ISSUE 6: Robust SIP participant detection using multiple signals.
    
    SIP participants can have various identity formats:
    - "sip_xxx", "sip-xxx", "sip"
    - "pstn_xxx", "pstn"
    - "inbound_xxx"
    - "tel:xxx"
    - "trunk_xxx"
    - "gateway_xxx"
    
    This function uses multiple detection methods:
    1. Check metadata for SIP/PSTN indicators
    2. Check attributes for SIP header keys (sip.*, sip.h.*, lk_*)
    3. Check identity prefix as fallback
    
    Returns True if the participant is identified as a SIP caller.
    """
    # Method 1: Check metadata for SIP/PSTN indicators
    metadata = getattr(p, "metadata", None) or ""
    if metadata:
        metadata_lower = metadata.lower()
        if "sip" in metadata_lower or "pstn" in metadata_lower or "telephony" in metadata_lower:
            return True
    
    # Method 2: Check attributes for SIP header keys (most reliable)
    attrs = getattr(p, "attributes", {}) or {}
    for key in attrs.keys():
        # LiveKit SIP headers are prefixed with "sip." or "sip.h."
        if key.startswith("sip.") or key.startswith("sip.h.") or key.startswith("lk_"):
            return True
    
    # Method 3: Check identity prefix (fallback, non-authoritative but useful)
    identity = getattr(p, "identity", "") or ""
    identity_lower = identity.lower()
    sip_prefixes = ("sip", "pstn", "inbound", "gateway", "tel", "trunk")
    for prefix in sip_prefixes:
        if identity_lower.startswith(prefix):
            return True
        if identity_lower.startswith(f"{prefix}_") or identity_lower.startswith(f"{prefix}-"):
            return True
    
    return False


def count_sip_attributes(p) -> int:
    """
    Count the number of SIP-related attributes on a participant.
    Used to select the best SIP participant when multiple are found.
    """
    attrs = getattr(p, "attributes", {}) or {}
    count = 0
    for key in attrs.keys():
        if key.startswith("sip.") or key.startswith("sip.h.") or key.startswith("lk_"):
            count += 1
    return count


async def extract_tenant_identity_from_sip(ctx: agents.JobContext, max_wait_seconds: float = 3.0) -> Dict[str, Optional[str]]:
    """
    Extract tenant identity from SIP participant attributes.
    
    FIX ISSUE 6: Comprehensive SIP attribute validation with fallback mappings
    and robust SIP participant detection.
    
    This is the PRIMARY method for multi-tenant routing.
    
    Returns a dict with:
    - tenant_id: The tenant identifier (REQUIRED for config lookup)
    - call_id: Unique per-call identifier (for concurrency isolation)
    - caller_number: The phone number of the caller (for logging)
    - called_number: The phone number that was called (for logging)
    
    SIP Header to Attribute Mapping:
    - Twilio sends: X-LK-TenantId=abc
    - LiveKit maps to: sip.h.x-lk-tenantid=abc (lowercase)
    
    The function checks multiple attribute names to handle different LiveKit SDK versions.
    """
    result = {
        "tenant_id": None,
        "call_id": None,
        "caller_number": None,
        "called_number": None,
    }
    
    try:
        # Wait for SIP participant to join (with timeout)
        wait_interval = 0.1
        waited = 0.0
        sip_participant = None
        
        while waited < max_wait_seconds:
            # FIX ISSUE 6: Use robust SIP participant detection
            # instead of relying on identity prefix alone
            all_participants = list(ctx.room.remote_participants.values())
            sip_participants = [p for p in all_participants if is_sip_participant(p)]
            
            if sip_participants:
                # If multiple SIP participants found, select the one with most SIP attributes
                if len(sip_participants) > 1:
                    logger.info(f"[TENANT IDENTITY] Found {len(sip_participants)} SIP participants, selecting best match")
                    sip_participant = max(sip_participants, key=count_sip_attributes)
                else:
                    sip_participant = sip_participants[0]
                break
            
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        if not sip_participant:
            # FIX ISSUE 6: Enhanced defensive logging
            logger.error(f"[TENANT IDENTITY] ✗ No SIP participants found in room after waiting {waited:.1f}s")
            all_participants = list(ctx.room.remote_participants.values())
            logger.error(f"[TENANT IDENTITY] ✗ Total participants in room: {len(all_participants)}")
            for p in all_participants:
                p_identity = getattr(p, "identity", "unknown")
                p_metadata = getattr(p, "metadata", "")
                p_attrs = list(getattr(p, "attributes", {}).keys())
                logger.error(f"[TENANT IDENTITY] ✗   - identity='{p_identity}', metadata='{p_metadata}', attrs={p_attrs}")
            logger.error(f"[TENANT IDENTITY] ✗ None of the participants matched SIP detection criteria")
            return result
        
        logger.info(f"[TENANT IDENTITY] ✓ Found SIP participant: {sip_participant.identity}")
        
        attrs = sip_participant.attributes
        
        # Log ALL attributes for debugging (FIX ISSUE 6: better diagnostics)
        logger.info(f"[TENANT IDENTITY] === ALL SIP PARTICIPANT ATTRIBUTES ===")
        for key, value in sorted(attrs.items()):
            logger.info(f"[TENANT IDENTITY]   {key} = {value}")
        logger.info(f"[TENANT IDENTITY] =====================================")
        
        # ========================================
        # EXTRACT TENANT ID (REQUIRED)
        # FIX ISSUE 6: Comprehensive fallback mapping
        # ========================================
        # LiveKit normalizes SIP headers to lowercase with sip.h. prefix
        # Try multiple variations to handle different SDK versions
        tenant_id_keys = [
            # Configured attribute name
            LIVEKIT_SIP_ATTRIBUTE_TENANT_ID,
            # LiveKit's lowercase mapping of X-LK-TenantId
            "sip.h.x-lk-tenantid",
            # Direct header name (some SDK versions)
            LIVEKIT_SIP_HEADER_TENANT_ID,
            "X-LK-TenantId",
            "x-lk-tenantid",
            # Alternative names
            "lk_tenant_id",
            "tenant_id",
            "tenantId",
            "sip.tenant_id",
        ]
        
        tenant_id = None
        for attr_key in tenant_id_keys:
            value = attrs.get(attr_key)
            if value:
                tenant_id = value.strip()
                logger.info(f"[TENANT IDENTITY] ✓ Found tenant_id via key '{attr_key}': {tenant_id}")
                break
        
        if tenant_id:
            result["tenant_id"] = tenant_id
        else:
            # FIX ISSUE 6: Log detailed error to help diagnose SIP header issues
            logger.error(f"[TENANT IDENTITY] ✗ Could not find tenant_id in SIP attributes!")
            logger.error(f"[TENANT IDENTITY] ✗ Checked keys: {tenant_id_keys}")
            logger.error(f"[TENANT IDENTITY] ✗ This usually means Twilio SIP URI formatting is incorrect.")
            logger.error(f"[TENANT IDENTITY] ✗ Expected format: sip:agent@domain?X-LK-TenantId=xxx&X-LK-CallId=yyy")
        
        # ========================================
        # EXTRACT CALL ID (FOR CONCURRENCY)
        # FIX ISSUE 6: Comprehensive fallback mapping
        # ========================================
        call_id_keys = [
            # Configured attribute name
            LIVEKIT_SIP_ATTRIBUTE_CALL_ID,
            # LiveKit's lowercase mapping of X-LK-CallId
            "sip.h.x-lk-callid",
            # Direct header name
            LIVEKIT_SIP_HEADER_CALL_ID,
            "X-LK-CallId",
            "x-lk-callid",
            # Alternative names
            "lk_call_id",
            "call_id",
            "callId",
            "sip.callID",
            "sip.call_id",
        ]
        
        call_id = None
        for attr_key in call_id_keys:
            value = attrs.get(attr_key)
            if value:
                call_id = value.strip()
                logger.info(f"[TENANT IDENTITY] ✓ Found call_id via key '{attr_key}': {call_id}")
                break
        
        if call_id:
            result["call_id"] = call_id
        else:
            # Generate a fallback call_id from participant identity
            # Remove common prefixes to get a cleaner identifier
            fallback_id = sip_participant.identity
            for prefix in ["sip_", "sip-", "pstn_", "pstn-", "inbound_", "inbound-", "tel:", "trunk_"]:
                if fallback_id.lower().startswith(prefix):
                    fallback_id = fallback_id[len(prefix):]
                    break
            result["call_id"] = fallback_id[:12]
            logger.warning(f"[TENANT IDENTITY] Using fallback call_id from participant: {result['call_id']}")
        
        # ========================================
        # EXTRACT PHONE NUMBERS (FOR LOGGING)
        # ========================================
        import re
        
        # Caller number (From)
        caller_keys = ["sip.callerPhoneNumber", "sip.h.from", "sip.from"]
        for key in caller_keys:
            caller = attrs.get(key)
            if caller:
                if "sip:" in caller:
                    match = re.search(r'sip:(\+?\d+)@', caller)
                    if match:
                        caller = match.group(1)
                result["caller_number"] = caller
                logger.info(f"[TENANT IDENTITY] Caller number: {result['caller_number']}")
                break
        
        # Called number (To)
        called_keys = [
            # Configured attribute name
            LIVEKIT_SIP_ATTRIBUTE_CALLED_NUMBER,
            # LiveKit's lowercase mapping
            "sip.h.x-lk-callednumber",
            LIVEKIT_SIP_HEADER_CALLED_NUMBER,
            "lk_called_number",
            "sip.trunkPhoneNumber",
            "sip.h.to",
            "sip.to",
        ]
        for key in called_keys:
            called = attrs.get(key)
            if called:
                if "sip:" in called:
                    match = re.search(r'sip:(\+?\d+)@', called)
                    if match:
                        called = match.group(1)
                result["called_number"] = called
                logger.info(f"[TENANT IDENTITY] Called number: {result['called_number']}")
                break
        
        return result
        
    except Exception as e:
        logger.error(f"[TENANT IDENTITY] Error extracting tenant identity: {e}", exc_info=True)
        return result


async def get_config_by_twilio_callsid(twilio_call_sid: str, max_retries: int = 5, retry_delay: float = 0.5) -> Optional[Dict[str, Any]]:
    """
    Retrieve call configuration from Redis by Twilio CallSid.
    
    This is the PRIMARY lookup method because:
    - sip.twilio.callSid is ALWAYS available in SIP participant attributes
    - Custom SIP headers via query params are NOT forwarded by Twilio to LiveKit
    
    Config is stored under: call_config:<twilio_call_sid>
    
    TIMING FIX: The worker may start BEFORE the backend finishes storing the config.
    This function retries the lookup with exponential backoff to handle this race condition.
    
    Returns the full config including tenant_id, call_id, agent_data, etc.
    Returns None if config not found after all retries.
    """
    config_key = f"call_config:{twilio_call_sid}"
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = retry_delay * (2 ** (attempt - 1))  # Exponential backoff: 0.5, 1, 2, 4 seconds
                logger.info(f"[WORKER REDIS] Retry {attempt}/{max_retries} - waiting {wait_time}s before next attempt...")
                await asyncio.sleep(wait_time)
            
            logger.info(f"[WORKER REDIS] Looking up config: {config_key} (attempt {attempt + 1}/{max_retries})")
            
            config_data = await async_redis_client.get(config_key)
            if config_data:
                config = json.loads(config_data)
                logger.info(f"[WORKER REDIS] ✓ Found config by Twilio CallSid (attempt {attempt + 1})")
                logger.info(f"[WORKER REDIS] Config details:")
                logger.info(f"  - tenant_id: {config.get('tenant_id')}")
                logger.info(f"  - call_id: {config.get('call_id')}")
                logger.info(f"  - agent_id: {config.get('agent_id')}")
                logger.info(f"  - voice_id: {config.get('voice_id')}")
                logger.info(f"  - service_type: {config.get('service_type')}")
                logger.info(f"  - agent_data keys: {list(config.get('agent_data', {}).keys())}")
                return config
            
            if attempt < max_retries - 1:
                logger.warning(f"[WORKER REDIS] Config not found yet, will retry...")
            
        except Exception as e:
            logger.error(f"[WORKER REDIS] ✗ Error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"[WORKER REDIS] ✗ All retries exhausted", exc_info=True)
    
    logger.error(f"[WORKER REDIS] ✗ No config found for Twilio CallSid after {max_retries} attempts: {twilio_call_sid}")
    return None


async def get_tenant_config(tenant_id: str, call_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve tenant configuration from Redis (legacy/fallback method).
    
    Config is stored per-call under: tenant_config:<tenant_id>:<call_id>
    This is kept for backward compatibility but the primary method is now
    get_config_by_twilio_callsid().
    
    Returns None if config not found (worker should FAIL, not use defaults).
    """
    try:
        # PRIMARY: Per-call config key (most specific)
        config_key = f"tenant_config:{tenant_id}:{call_id}"
        logger.info(f"[WORKER REDIS] Looking up config with key: {config_key}")
        
        config_data = await async_redis_client.get(config_key)
        if config_data:
            config = json.loads(config_data)
            logger.info(f"[WORKER REDIS] ✓ Found per-call config for tenant {tenant_id}, call {call_id}")
            logger.info(f"[WORKER REDIS] Config details:")
            logger.info(f"  - agent_id: {config.get('agent_id')}")
            logger.info(f"  - voice_id: {config.get('voice_id')}")
            logger.info(f"  - service_type: {config.get('service_type')}")
            logger.info(f"  - agent_data keys: {list(config.get('agent_data', {}).keys())}")
            return config
        
        # FALLBACK: Tenant-level config (for backwards compatibility)
        tenant_config_key = f"tenant_config:{tenant_id}"
        logger.info(f"[WORKER REDIS] Per-call config not found, trying tenant key: {tenant_config_key}")
        
        config_data = await async_redis_client.get(tenant_config_key)
        if config_data:
            config = json.loads(config_data)
            logger.info(f"[WORKER REDIS] ✓ Found tenant-level config for {tenant_id}")
            return config
        
        logger.error(f"[WORKER REDIS] ✗ No tenant configuration found for tenant_id={tenant_id}, call_id={call_id}")
        return None
        
    except Exception as e:
        logger.error(f"[WORKER REDIS] ✗ Error retrieving tenant config from Redis: {e}", exc_info=True)
        return None


def build_agent_instructions(config: Dict[str, Any]) -> str:
    """
    Build agent instructions from tenant configuration using service-specific templates.
    The templates from app/core/prompts.py contain comprehensive service-specific workflows.
    
    NOTE: This function requires a valid config. It should NEVER be called with None.
    """
    agent_data = config.get("agent_data", {})
    agent_name = agent_data.get("name", "Assistant")
    service_type = config.get("service_type", "Home Services")
    language = agent_data.get("language", "en-US")

    logger.info(f"[INSTRUCTIONS] Building instructions from SERVICE TEMPLATE")
    logger.info(f"[INSTRUCTIONS] Agent name: {agent_name}")
    logger.info(f"[INSTRUCTIONS] Service type: {service_type}")
    logger.info(f"[INSTRUCTIONS] Language: {language}")

    # Use the service-specific template from app/core/prompts.py
    instructions = get_template(service_type=service_type, agent_name=agent_name)

    logger.info(f"[INSTRUCTIONS] ✓ Using {service_type} template with agent name: {agent_name}")
    return instructions


def extract_greeting_message(config: Dict[str, Any]) -> Optional[str]:
    """
    Extract the custom greeting message from tenant configuration.
    This greeting will be used as the agent's initial spoken message.
    
    NOTE: This function requires a valid config. It should NEVER be called with None.
    """
    agent_data = config.get("agent_data", {})
    greeting = agent_data.get("greeting_message", "")

    if greeting and greeting.strip():
        logger.info(f"[GREETING] Found custom greeting: {greeting[:100]}...")
        return greeting.strip()
    else:
        logger.info("[GREETING] No custom greeting found, will use default")
        return None


async def handle_missing_config(session: AgentSession) -> None:
    """
    Handle the case where tenant config is missing.
    
    This MUST fail the call gracefully - NO fallback to defaults.
    Per requirements: "Worker MUST NOT fall back to a generic agent."
    """
    error_message = (
        "We are unable to connect this call at the moment. "
        "Please try again later or contact support."
    )
    
    try:
        # Say error message to caller
        await session.generate_reply(instructions=f"Say exactly: '{error_message}'")
        
        # Wait a moment for message to be spoken
        await asyncio.sleep(3)
        
        # Close the session
        await session.aclose()
    except Exception as e:
        logger.error(f"Error handling missing config: {e}")


async def entrypoint(ctx: agents.JobContext):
    """
    Main entrypoint for the LiveKit voice agent worker.
    
    This is called when LiveKit dispatches a job based on the dispatch rule.
    
    CANONICAL TELEPHONY FLOW:
    1. Twilio PSTN call → Backend webhook
    2. Backend stores config under call_config:<twilio_call_sid>
    3. Backend returns TwiML <Dial><Sip> to LiveKit
    4. LiveKit dispatch rule creates room: call-{phoneNumber}_{randomSuffix}
    5. Dispatch rule launches this worker (agent_name="voice-agent")
    6. Worker reads sip.twilio.callSid from SIP participant attributes
    7. Worker loads config from Redis using Twilio CallSid
    8. Worker handles the call with tenant-specific config
    
    IMPORTANT: Worker uses sip.twilio.callSid for config lookup (NOT custom headers).
    """
    logger.info("=" * 80)
    logger.info(f"[WORKER ENTRYPOINT] Voice agent worker starting")
    logger.info(f"[WORKER ENTRYPOINT] Room name (for logging only, NOT for config): {ctx.room.name}")
    logger.info("=" * 80)

    # Pre-warm VAD model (lightweight if already loaded)
    prewarm_vad()

    # Connect to the LiveKit room FIRST
    # This ensures the SIP participant has joined before we try to read attributes
    await ctx.connect()
    logger.info(f"[WORKER ENTRYPOINT] Connected to room")

    # Wait a moment for SIP participant to join and attributes to be available
    await asyncio.sleep(0.5)
    
    # ========================================
    # STEP 1: Extract CallSid from SIP participant
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 1: Extracting CallSid from SIP participant...")
    
    # Find the SIP participant and get their attributes
    original_call_sid = None
    sip_participant = None
    
    all_participants = list(ctx.room.remote_participants.values())
    logger.info(f"[WORKER ENTRYPOINT] Found {len(all_participants)} remote participants")
    
    for p in all_participants:
        if is_sip_participant(p):
            sip_participant = p
            attrs = getattr(p, "attributes", {}) or {}
            
            # Log ALL attributes for debugging
            logger.info(f"[WORKER ENTRYPOINT] === SIP PARTICIPANT ATTRIBUTES ===")
            for key, value in sorted(attrs.items()):
                logger.info(f"[WORKER ENTRYPOINT]   {key} = {value}")
            logger.info(f"[WORKER ENTRYPOINT] ==================================")
            
            # PRIORITY 1: Extract from our custom header x-lk-callid (passed via SIP URI query params)
            # This is the ORIGINAL Twilio CallSid from the inbound webhook
            original_call_sid = attrs.get("sip.h.x-lk-callid")
            if original_call_sid:
                logger.info(f"[WORKER ENTRYPOINT] ✓ Found original CallSid from x-lk-callid: {original_call_sid}")
                break
            
            # FALLBACK: Try sip.twilio.callSid (this is the SIP leg CallSid, NOT the original!)
            # This won't match Redis but log it for debugging
            sip_leg_callsid = attrs.get("sip.twilio.callSid")
            if sip_leg_callsid:
                logger.warning(f"[WORKER ENTRYPOINT] ⚠ x-lk-callid not found, found sip.twilio.callSid: {sip_leg_callsid}")
                logger.warning(f"[WORKER ENTRYPOINT] ⚠ This is the SIP leg CallSid, NOT the original webhook CallSid!")
                logger.warning(f"[WORKER ENTRYPOINT] ⚠ This usually means SIP URI query params weren't forwarded")
                # Use it as fallback anyway
                original_call_sid = sip_leg_callsid
                break
    
    if not original_call_sid:
        logger.error(f"[WORKER ENTRYPOINT] ✗ CRITICAL: Could not find CallSid in SIP attributes")
        logger.error(f"[WORKER ENTRYPOINT] ✗ Checked: sip.h.x-lk-callid, sip.twilio.callSid")
        logger.error(f"[WORKER ENTRYPOINT] This call cannot proceed without CallSid")
        
        # Create a minimal session just to say error message
        error_vad = get_cached_vad()
        error_session = AgentSession(
            stt=deepgram.STT(model="nova-2-general", language="en-US"),
            llm=google.LLM(model="gemini-2.0-flash"),
            tts=elevenlabs.TTS(api_key=ELEVEN_API_KEY),
            vad=error_vad,
        )
        error_agent = VoiceAgent(instructions="You are an error handler. Say the error message exactly as instructed.")
        await error_session.start(room=ctx.room, agent=error_agent)
        await handle_missing_config(error_session)
        return
    
    # ========================================
    # STEP 2: Load configuration from Redis using original CallSid
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 2: Loading config from Redis by CallSid: {original_call_sid}")
    config = await get_config_by_twilio_callsid(original_call_sid)

    if not config:
        logger.error(f"[WORKER ENTRYPOINT] ✗ CRITICAL: No configuration found for CallSid: {original_call_sid}")
        logger.error(f"[WORKER ENTRYPOINT] Failing call - NO FALLBACK TO DEFAULTS")
        
        # Create a minimal session to say error message
        error_vad = get_cached_vad()
        error_session = AgentSession(
            stt=deepgram.STT(model="nova-2-general", language="en-US"),
            llm=google.LLM(model="gemini-2.0-flash"),
            tts=elevenlabs.TTS(api_key=ELEVEN_API_KEY),
            vad=error_vad,
        )
        error_agent = VoiceAgent(instructions="You are an error handler. Say the error message exactly as instructed.")
        await error_session.start(room=ctx.room, agent=error_agent)
        await handle_missing_config(error_session)
        return

    # Extract tenant_id and call_id from config (stored by backend)
    tenant_id = config.get("tenant_id")
    call_id = config.get("call_id")
    
    logger.info(f"[WORKER ENTRYPOINT] ✓ Configuration loaded successfully")
    logger.info(f"[WORKER ENTRYPOINT]   tenant_id: {tenant_id}")
    logger.info(f"[WORKER ENTRYPOINT]   call_id: {call_id}")
    logger.info(f"[WORKER ENTRYPOINT]   twilio_call_sid: {twilio_call_sid}")

    # ========================================
    # STEP 3: Build agent instructions from config
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 3: Building agent instructions...")
    instructions = build_agent_instructions(config)
    logger.info(f"[WORKER ENTRYPOINT] Instructions preview (first 150 chars): {instructions[:150]}...")

    # ========================================
    # STEP 4: Extract custom greeting
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 4: Extracting custom greeting...")
    custom_greeting = extract_greeting_message(config)

    # ========================================
    # STEP 5: Create voice agent with tenant config
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 5: Creating voice agent...")
    voice_agent = VoiceAgent(instructions=instructions)
    logger.info(f"[WORKER ENTRYPOINT] ✓ Voice agent created")

    # ========================================
    # STEP 6: Configure TTS with tenant's voice
    # ========================================
    logger.info(f"[WORKER ENTRYPOINT] Step 6: Configuring TTS...")
    voice_id = config.get("voice_id")
    language_code = "en"

    if voice_id:
        logger.info(f"[WORKER TTS] Using voice_id from config: {voice_id}")
        agent_data = config.get("agent_data", {})
        if agent_data.get("language"):
            language_code = agent_data.get("language", "en-US").split("-")[0]
            logger.info(f"[WORKER TTS] Language code: {language_code}")
    else:
        logger.warning("[WORKER TTS] No voice_id in config, using default voice")

    tts = get_tts_service(voice_id, language_code)

    # ========================================
    # STEP 7: Create and start agent session
    # ========================================
    vad = None
    try:
        vad = ctx.proc.userdata.get("vad")
    except Exception:
        vad = None
    if vad is None:
        vad = get_cached_vad()

    session = AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="en-US"),
        llm=google.LLM(model="gemini-2.0-flash"),
        tts=tts,
        vad=vad,
    )

    await session.start(
        room=ctx.room,
        agent=voice_agent,
    )
    logger.info("[WORKER ENTRYPOINT] ✓ Agent session started")

    # Setup session close handler
    closed_event = asyncio.Event()

    @session.on("close")
    def on_close(ev: agents.CloseEvent):
        logger.info(f"Agent Session closed, reason: {ev}")
        logger.info("=" * 20)
        history_items = list(session.history.items)
        total_items = len(history_items)
        logger.info(f"Chat History (showing up to {MAX_HISTORY_LOG_LINES} messages, total={total_items})")

        for item in history_items[:MAX_HISTORY_LOG_LINES]:
            if item.type == "message":
                safe_text = item.text_content.replace("\n", "\\n")
                text = f"{item.role}: {safe_text}"
                if item.interrupted:
                    text += " (interrupted)"
                logger.info(text)

        if total_items > MAX_HISTORY_LOG_LINES:
            logger.info(
                f"... truncated {total_items - MAX_HISTORY_LOG_LINES} additional message(s) to prevent log blocking ..."
            )
        logger.info("=" * 20)
        
        # Cleanup: Delete per-call config from Redis after call ends
        async def cleanup_config():
            try:
                config_key = f"tenant_config:{tenant_id}:{call_id}"
                await async_redis_client.delete(config_key)
                logger.info(f"[CLEANUP] Deleted per-call config: {config_key}")
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed to delete config: {e}")
        
        asyncio.create_task(cleanup_config())
        closed_event.set()

    # ========================================
    # STEP 8: Send initial greeting
    # ========================================
    logger.info("[WORKER ENTRYPOINT] Step 8: Sending initial greeting...")
    if custom_greeting:
        logger.info(f"[GREETING] Using CUSTOM greeting: {custom_greeting[:100]}...")
        await session.generate_reply(instructions=f"Greet the user by saying exactly: '{custom_greeting}'")
    else:
        logger.info("[GREETING] Using DEFAULT greeting (generated from instructions)")
        await session.generate_reply()

    logger.info("[WORKER ENTRYPOINT] ✓ Initial greeting sent successfully")
    logger.info(f"[WORKER ENTRYPOINT] ✓ Call active for tenant {tenant_id}")

    # Wait for the session to close
    await closed_event.wait()
    logger.info(f"[WORKER ENTRYPOINT] Voice agent worker completed for tenant {tenant_id}")


if __name__ == "__main__":
    """Run the worker when executed directly."""
    import multiprocessing

    multiprocessing.freeze_support()

    # IMPORTANT: agent_name MUST match the dispatch rule configuration
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
            ws_url=LIVEKIT_URL,
            prewarm_fnc=prewarm_vad,
            agent_name="voice-agent",  # MUST match dispatch rule's roomConfig.agents[].agentName
        )
    )
