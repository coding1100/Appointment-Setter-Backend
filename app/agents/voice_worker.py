"""
LiveKit Voice Agent Worker
This worker connects to LiveKit and handles voice agent sessions.
Based on the LiveKit agents framework pattern.

Works with LiveKit Individual dispatch rule where room names are:
  inbound_{callerNumber}_{randomSuffix}

Config is stored in Redis by caller phone number and looked up when worker starts.
"""

import asyncio
import json
import logging
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
)
from app.core.prompts import get_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgentWorker")

TTS_CACHE: Dict[str, elevenlabs.TTS] = {}
DEFAULT_TTS_CACHE_KEY = "__default__"
MAX_HISTORY_LOG_LINES = 40

# VAD settings optimized for telephony
# Lower thresholds = more responsive but may trigger on noise
# Higher thresholds = more stable but may miss quiet speech
VAD_SETTINGS = {
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


def prewarm_vad():
    """Pre-warm VAD model to prevent cold start delays."""
    try:
        logger.info("Pre-warming VAD model...")
        # Use the cached VAD getter to ensure model is loaded once
        get_cached_vad()
        logger.info("VAD model pre-warmed successfully")
    except Exception as e:
        logger.warning(f"Failed to pre-warm VAD model: {e}")


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


def extract_caller_from_room_name(room_name: str) -> Optional[str]:
    """
    Extract caller phone number from LiveKit Individual dispatch room name.
    
    Room name format: inbound_+14438600638_w9TNRqtPr5A2
                      {prefix}_{caller}_{suffix}
    
    Returns the caller number (e.g., "+14438600638") or None if parsing fails.
    """
    if not room_name:
        return None
    
    # Handle both underscore (LiveKit) and dash (legacy) separators
    if room_name.startswith("inbound_"):
        # LiveKit Individual dispatch format: inbound_+14438600638_suffix
        parts = room_name.split("_")
        if len(parts) >= 2:
            # parts[0] = "inbound", parts[1] = "+14438600638", parts[2] = suffix
            caller = parts[1]
            logger.info(f"[ROOM PARSE] Extracted caller '{caller}' from room '{room_name}'")
            return caller
    elif room_name.startswith("inbound-"):
        # Legacy format: inbound-14438600638-suffix
        parts = room_name.split("-")
        if len(parts) >= 2:
            caller = parts[1]
            # Add + prefix if missing
            if not caller.startswith("+"):
                caller = f"+{caller}"
            logger.info(f"[ROOM PARSE] Extracted caller '{caller}' from legacy room '{room_name}'")
            return caller
    
    logger.warning(f"[ROOM PARSE] Could not extract caller from room name: {room_name}")
    return None


async def extract_called_number_from_attributes(ctx: agents.JobContext, max_wait_seconds: float = 2.0) -> Optional[str]:
    """
    Extract called phone number (to_number) from SIP participant attributes.
    
    The backend passes to_number via SIP header X-LK-CalledNumber,
    which LiveKit maps to participant attribute lk_called_number.
    
    Waits for SIP participant to join if not immediately available.
    """
    try:
        # Wait for SIP participant to join (with timeout)
        wait_interval = 0.1
        waited = 0.0
        sip_participant = None
        
        while waited < max_wait_seconds:
            # Get SIP participant (the caller)
            sip_participants = [p for p in ctx.room.remote_participants.values() if p.identity.startswith("sip_")]
            if sip_participants:
                sip_participant = sip_participants[0]
                break
            
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        if not sip_participant:
            logger.warning(f"[ATTRIBUTES] No SIP participants found in room after waiting {waited:.1f}s")
            logger.info(f"[ATTRIBUTES] Current participants: {[p.identity for p in ctx.room.remote_participants.values()]}")
            return None
        
        logger.info(f"[ATTRIBUTES] Found SIP participant: {sip_participant.identity}")
        logger.info(f"[ATTRIBUTES] Participant attributes: {dict(sip_participant.attributes)}")
        
        # Try to get called number from participant attributes
        # LiveKit maps SIP header X-LK-CalledNumber to attribute lk_called_number
        from app.core.config import LIVEKIT_SIP_ATTRIBUTE_CALLED_NUMBER
        called_number = sip_participant.attributes.get(LIVEKIT_SIP_ATTRIBUTE_CALLED_NUMBER)
        if called_number:
            logger.info(f"[ATTRIBUTES] ✓ Extracted called number '{called_number}' from attribute '{LIVEKIT_SIP_ATTRIBUTE_CALLED_NUMBER}'")
            return called_number
        
        # Fallback: try alternative attribute names
        from app.core.config import LIVEKIT_SIP_HEADER_CALLED_NUMBER
        for attr_key in [LIVEKIT_SIP_HEADER_CALLED_NUMBER, "called_number", "to_number", "X-LK-CalledNumber"]:
            called_number = sip_participant.attributes.get(attr_key)
            if called_number:
                logger.info(f"[ATTRIBUTES] ✓ Extracted called number '{called_number}' from attribute '{attr_key}'")
                return called_number
        
        logger.warning(f"[ATTRIBUTES] ✗ Could not find called number in participant attributes.")
        logger.warning(f"[ATTRIBUTES] Available attributes: {list(sip_participant.attributes.keys())}")
        logger.warning(f"[ATTRIBUTES] All attribute values: {dict(sip_participant.attributes)}")
        return None
        
    except Exception as e:
        logger.error(f"[ATTRIBUTES] Error extracting called number from attributes: {e}", exc_info=True)
        return None


async def get_agent_config(room_name: str, ctx: Optional[agents.JobContext] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve agent configuration from Redis.
    
    CORRECT APPROACH: Look up config by called number (to_number), not caller number.
    The agent config is tied to the Twilio phone number that was called, not the caller.
    
    Lookup order:
    1. By called number (from SIP participant attributes) - CORRECT approach
    2. By room name - for backward compatibility with Direct dispatch
    """
    try:
        # Step 1: Get called number from SIP participant attributes and look up config
        if ctx:
            called_number = await extract_called_number_from_attributes(ctx)
            if called_number:
                # Normalize the called number for consistent lookup
                from app.utils.phone_number import normalize_phone_number_safe
                normalized_called = normalize_phone_number_safe(called_number)
                if normalized_called:
                    called_config_key = f"livekit:called_number_config:{normalized_called}"
                    logger.info(f"[WORKER REDIS] Trying called-number-based lookup with key: {called_config_key}")
                    
                    config_data = await async_redis_client.get(called_config_key)
                    if config_data:
                        config = json.loads(config_data)
                        logger.info(f"[WORKER REDIS] ✓ Found config by called number: {normalized_called}")
                        logger.info(f"[WORKER REDIS] Config details:")
                        logger.info(f"  - agent_id: {config.get('agent_id')}")
                        logger.info(f"  - voice_id: {config.get('voice_id')}")
                        logger.info(f"  - service_type: {config.get('service_type')}")
                        logger.info(f"  - agent_data keys: {list(config.get('agent_data', {}).keys())}")
                        return config
                    else:
                        logger.warning(f"[WORKER REDIS] No config found for called number {normalized_called}, trying room-based lookup...")
                else:
                    logger.warning(f"[WORKER REDIS] Could not normalize called number: {called_number}")
            else:
                logger.warning(f"[WORKER REDIS] Could not extract called number from attributes, trying room-based lookup...")

        # Step 2: Fall back to room name lookup (backward compatibility with Direct dispatch)
        room_config_key = f"livekit:room_config:{room_name}"
        logger.info(f"[WORKER REDIS] Trying room-based lookup with key: {room_config_key}")
        
        config_data = await async_redis_client.get(room_config_key)
        if config_data:
            config = json.loads(config_data)
            logger.info(f"[WORKER REDIS] ✓ Found config by room name: {room_name}")
            logger.info(f"[WORKER REDIS] Config details:")
            logger.info(f"  - agent_id: {config.get('agent_id')}")
            logger.info(f"  - voice_id: {config.get('voice_id')}")
            logger.info(f"  - service_type: {config.get('service_type')}")
            return config

        logger.warning(f"[WORKER REDIS] ✗ No agent configuration found (tried called number and room lookups)")
        return None
        
    except Exception as e:
        logger.error(f"[WORKER REDIS] ✗ Error retrieving agent config from Redis: {e}", exc_info=True)
        return None


def build_agent_instructions(config: Optional[Dict[str, Any]]) -> str:
    """
    Build agent instructions from configuration using service-specific templates.
    The templates from app/core/prompts.py contain comprehensive service-specific workflows.
    """
    # Extract agent data
    if config and config.get("agent_data"):
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
    else:
        # Fallback to default if no config
        logger.warning("[INSTRUCTIONS] No config found, using default Home Services template")
        return get_template(service_type="Home Services", agent_name="Assistant")


def extract_greeting_message(config: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Extract the custom greeting message from agent configuration.
    This greeting will be used as the agent's initial spoken message.
    """
    if config and config.get("agent_data"):
        agent_data = config.get("agent_data", {})
        greeting = agent_data.get("greeting_message", "")

        if greeting and greeting.strip():
            logger.info(f"[GREETING] Found custom greeting: {greeting[:100]}...")
            return greeting.strip()
        else:
            logger.info("[GREETING] No custom greeting found, will use default")
            return None
    else:
        logger.info("[GREETING] No config found, will use default greeting")
        return None


async def entrypoint(ctx: agents.JobContext):
    """
    Main entrypoint for the LiveKit voice agent worker.
    This is called when a participant joins a room.
    
    Room name format from Individual dispatch: inbound_+14438600638_randomSuffix
    We extract the caller number and look up config from Redis.
    """
    room_name = ctx.room.name
    logger.info("=" * 80)
    logger.info(f"[WORKER ENTRYPOINT] Starting voice agent worker for room: {room_name}")
    logger.info("=" * 80)

    # Pre-warm VAD model (lightweight if already loaded)
    prewarm_vad()

    # Connect to the LiveKit room FIRST
    # This ensures the SIP participant has joined before we try to read attributes
    await ctx.connect()
    logger.info(f"Connected to room: {room_name}")

    # Wait a moment for SIP participant to join and attributes to be available
    await asyncio.sleep(0.5)
    
    # Now retrieve agent configuration from Redis
    # Config is stored by called phone number (to_number), not caller number
    # We get to_number from SIP participant attributes (passed via SIP header)
    logger.info(f"[WORKER ENTRYPOINT] Step 1: Retrieving agent configuration...")
    config = await get_agent_config(room_name, ctx)

    if config:
        logger.info(f"[WORKER ENTRYPOINT] ✓ Configuration retrieved successfully")
    else:
        logger.warning(f"[WORKER ENTRYPOINT] ✗ No configuration found, will use defaults")

    # Build agent instructions based on configuration (from service templates)
    logger.info(f"[WORKER ENTRYPOINT] Step 2: Building agent instructions from templates...")
    instructions = build_agent_instructions(config)
    logger.info(f"[WORKER ENTRYPOINT] Instructions preview (first 150 chars): {instructions[:150]}...")

    # Extract custom greeting message (separate from system instructions)
    logger.info(f"[WORKER ENTRYPOINT] Step 2b: Extracting custom greeting message...")
    custom_greeting = extract_greeting_message(config)

    # Create the voice agent
    logger.info(f"[WORKER ENTRYPOINT] Step 3: Creating voice agent...")
    voice_agent = VoiceAgent(instructions=instructions)
    logger.info(f"[WORKER ENTRYPOINT] ✓ Voice agent created")

    # Configure TTS based on agent voice_id
    logger.info(f"[WORKER ENTRYPOINT] Step 4: Configuring TTS...")
    voice_id = None
    language_code = "en"

    if config and config.get("voice_id"):
        voice_id = config.get("voice_id")
        logger.info(f"[WORKER TTS] Found voice_id in config: {voice_id}")

        # Extract language code
        if config.get("agent_data") and config["agent_data"].get("language"):
            language_code = config["agent_data"].get("language", "en-US").split("-")[0]
            logger.info(f"[WORKER TTS] Language code: {language_code}")
    else:
        logger.warning("[WORKER TTS] No voice_id in config, will use default")

    tts = get_tts_service(voice_id, language_code)

    # Create the agent session with all components
    # OPTIMIZATION: Use cached VAD and faster models to prevent timeouts
    # Using cached VAD prevents model reload per call (major source of slowness)
    session = AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="en-US"),
        llm=google.LLM(model="gemini-2.0-flash"),
        tts=tts,
        vad=get_cached_vad(),
    )

    # Start the agent session (we already connected above)
    await session.start(
        room=ctx.room,
        agent=voice_agent,
    )
    logger.info("Agent session started")

    # Wait until the session is closed
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
        closed_event.set()

    # Send initial greeting
    logger.info("[WORKER ENTRYPOINT] Step 6: Sending initial greeting...")
    if custom_greeting:
        # Use custom greeting from agent configuration
        logger.info(f"[GREETING] Using CUSTOM greeting: {custom_greeting[:100]}...")
        await session.generate_reply(instructions=f"Greet the user by saying exactly: '{custom_greeting}'")
    else:
        # Use default greeting (agent will generate based on its instructions)
        logger.info("[GREETING] Using DEFAULT greeting (generated from instructions)")
        await session.generate_reply()

    logger.info("[WORKER ENTRYPOINT] ✓ Initial greeting sent successfully")

    # Wait for the session to close
    await closed_event.wait()
    logger.info("Voice agent worker completed")


if __name__ == "__main__":
    """Run the worker when executed directly."""
    import multiprocessing

    multiprocessing.freeze_support()

    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
            ws_url=LIVEKIT_URL,
        )
    )
