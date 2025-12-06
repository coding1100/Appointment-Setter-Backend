"""
LiveKit Voice Agent Worker
This worker connects to LiveKit and handles voice agent sessions.
Based on the LiveKit agents framework pattern.
"""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, Optional

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    RoomInputOptions,
    function_tool,
)
from livekit.plugins import deepgram, elevenlabs, google, silero

from app.core.async_redis import async_redis_client
from app.core.config import (
    DEEPGRAM_API_KEY,
    ELEVEN_API_KEY,
    GOOGLE_API_KEY,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_SIP_ATTRIBUTE_AGENT,
    LIVEKIT_SIP_ATTRIBUTE_CALL_KEY,
    LIVEKIT_SIP_ATTRIBUTE_CONFIG,
    LIVEKIT_SIP_ATTRIBUTE_TENANT,
    LIVEKIT_URL,
)
from app.core.prompts import get_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgentWorker")

TTS_CACHE: Dict[str, elevenlabs.TTS] = {}
DEFAULT_TTS_CACHE_KEY = "__default__"
MAX_HISTORY_LOG_LINES = 40

VAD_SETTINGS = {
    "min_speech_duration": 0.1,      # seconds
    "min_silence_duration": 0.5,     # seconds
    "prefix_padding_duration": 0.1,  # seconds
    "activation_threshold": 0.5,
}


def prewarm_vad():
    """Pre-warm VAD model to prevent cold start delays."""
    try:
        logger.info("Pre-warming VAD model...")
        vad = silero.VAD.load(**VAD_SETTINGS)
        # Run a dummy inference
        import numpy as np
        dummy_audio = np.zeros(1600, dtype=np.float32)  # 0.1s of silence
        # Just creating the iterator or processing a chunk warms it up
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


def _extract_participant_attributes(ctx: agents.JobContext) -> Dict[str, str]:
    """Normalize participant attribute structure into a simple dictionary."""
    attributes: Dict[str, str] = {}
    job = getattr(ctx, "job", None)
    participant = getattr(job, "participant", None) if job else None
    raw_attributes = getattr(participant, "attributes", None) if participant else None

    if not raw_attributes:
        return attributes

    if isinstance(raw_attributes, dict):
        return {str(key): value for key, value in raw_attributes.items() if value is not None}

    try:
        for entry in raw_attributes:
            key = getattr(entry, "key", None)
            value = getattr(entry, "value", None)
            if key and value is not None:
                attributes[str(key)] = value
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(f"[WORKER ENTRYPOINT] Failed to normalize participant attributes: {exc}")

    return attributes


def extract_call_metadata(ctx: agents.JobContext) -> Dict[str, Optional[str]]:
    """Extract high-level metadata (tenant, agent, call key) for logging and fallbacks."""
    attributes = _extract_participant_attributes(ctx)
    metadata = {
        "call_key": attributes.get(LIVEKIT_SIP_ATTRIBUTE_CALL_KEY),
        "tenant_id": attributes.get(LIVEKIT_SIP_ATTRIBUTE_TENANT),
        "agent_id": attributes.get(LIVEKIT_SIP_ATTRIBUTE_AGENT),
    }
    logger.info(f"[WORKER ENTRYPOINT] SIP attributes: {metadata}")
    return metadata


def load_config_from_attributes(ctx: agents.JobContext) -> Optional[Dict[str, Any]]:
    """Decode agent configuration embedded in SIP participant attributes."""
    attributes = _extract_participant_attributes(ctx)
    encoded_config = attributes.get(LIVEKIT_SIP_ATTRIBUTE_CONFIG)

    if not encoded_config:
        logger.info("[WORKER ATTRIBUTES] No embedded config attribute present")
        return None

    try:
        padding = "=" * (-len(encoded_config) % 4)
        decoded = base64.urlsafe_b64decode((encoded_config + padding).encode("utf-8")).decode("utf-8")
        config = json.loads(decoded)
        logger.info("[WORKER ATTRIBUTES] ✓ Loaded agent config from SIP attributes")
        return config
    except Exception as exc:
        logger.warning(f"[WORKER ATTRIBUTES] Failed to decode config from SIP attribute: {exc}")
        return None


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


async def get_agent_config(room_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve agent configuration for a room from Redis."""
    try:
        config_key = f"livekit:room_config:{room_name}"
        logger.info(f"[WORKER REDIS] Attempting to retrieve config with key: {config_key}")

        config_data = await async_redis_client.get(config_key)
        logger.info(f"[WORKER REDIS] Raw config data retrieved: {config_data}")

        if config_data:
            config = json.loads(config_data)
            logger.info(f"[WORKER REDIS] ✓ Parsed configuration successfully")
            logger.info(f"[WORKER REDIS] Config details:")
            logger.info(f"  - agent_id: {config.get('agent_id')}")
            logger.info(f"  - voice_id: {config.get('voice_id')}")
            logger.info(f"  - service_type: {config.get('service_type')}")
            logger.info(f"  - agent_data: {config.get('agent_data')}")
            return config
        else:
            # Try fallback lookup: if room_name is just "inbound-{caller_number}", 
            # it might have been created by dispatch rule differently than webhook expected
            # Also try if room_name has call_sid suffix, try without it
            logger.warning(f"[WORKER REDIS] ✗ No agent configuration found for room {room_name}, trying fallback lookup...")
            
            # Fallback 1: If room_name is "inbound-{caller_number}", it's already the fallback format
            # Fallback 2: If room_name is "inbound-{caller_number}-{call_sid}", try "inbound-{caller_number}"
            if room_name.startswith("inbound-"):
                parts = room_name.split("-")
                if len(parts) >= 2:
                    caller_number = parts[1]
                    # Try the other format (if current is with call_sid, try without; if without, try with common patterns)
                    fallback_room_name = f"inbound-{caller_number}"
                    if fallback_room_name != room_name:  # Only try if different
                        fallback_config_key = f"livekit:room_config:{fallback_room_name}"
                        logger.info(f"[WORKER REDIS] Trying fallback key: {fallback_config_key}")
                        fallback_config_data = await async_redis_client.get(fallback_config_key)
                        if fallback_config_data:
                            logger.info(f"[WORKER REDIS] ✓ Found config using fallback key: {fallback_config_key}")
                            config = json.loads(fallback_config_data)
                            logger.info(f"[WORKER REDIS] Config details:")
                            logger.info(f"  - agent_id: {config.get('agent_id')}")
                            logger.info(f"  - voice_id: {config.get('voice_id')}")
                            logger.info(f"  - service_type: {config.get('service_type')}")
                            logger.info(f"  - agent_data: {config.get('agent_data')}")
                            return config
            
            logger.warning(f"[WORKER REDIS] ✗ No agent configuration found for room {room_name} (tried fallback), using defaults")
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
    """
    room_name = ctx.room.name
    logger.info("=" * 80)
    logger.info(f"[WORKER ENTRYPOINT] Starting voice agent worker for room: {room_name}")
    logger.info("=" * 80)

    # Pre-warm VAD model (lightweight if already loaded)
    prewarm_vad()

    # Inspect SIP participant attributes for embedded metadata/config
    extract_call_metadata(ctx)
    attribute_config = load_config_from_attributes(ctx)

    # Retrieve agent configuration from Redis
    logger.info(f"[WORKER ENTRYPOINT] Step 1: Retrieving agent configuration...")
    if attribute_config:
        config = attribute_config
        logger.info("[WORKER ENTRYPOINT] Using agent config supplied via SIP attributes")
    else:
        config = await get_agent_config(room_name)

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
    # OPTIMIZATION: Use faster models and specific configurations to prevent timeouts
    session = AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="en-US"),
        llm=google.LLM(model="gemini-2.0-flash"),
        tts=tts,
        vad=silero.VAD.load(**VAD_SETTINGS),
    )

    # Connect to the LiveKit room
    await ctx.connect()
    logger.info(f"Connected to room: {room_name}")

    # Start the agent session
    await session.start(
        room=ctx.room,
        agent=voice_agent,
        room_input_options=RoomInputOptions(),
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
