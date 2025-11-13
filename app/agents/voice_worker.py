"""
LiveKit Voice Agent Worker
This worker connects to LiveKit and handles voice agent sessions.
Based on the LiveKit agents framework pattern.
"""
import os
import asyncio
import logging
import json
from typing import Optional, Dict, Any

from livekit import agents
from livekit.agents import (
    AgentSession,
    Agent,
    RoomInputOptions,
    function_tool,
)
from livekit.plugins import deepgram, silero, google, elevenlabs

from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    GOOGLE_API_KEY,
    DEEPGRAM_API_KEY,
    ELEVEN_API_KEY
)
from app.core.async_redis import async_redis_client
from app.core.prompts import get_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgentWorker")


class VoiceAgent(Agent):
    """Voice agent for handling customer interactions."""
    
    def __init__(self, instructions: str) -> None:
        super().__init__(
            tools=[],  # Add your tools here if needed
            instructions=instructions,
        )
        self._closing_task: Optional[asyncio.Task] = None

    @function_tool
    async def close_session(self):
        """Called when user wants to leave the conversation."""
        logger.info("Closing session from function tool")
        await self.session.generate_reply(instructions="say goodbye to the user")
        self._closing_task = asyncio.create_task(self.session.aclose())


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
            logger.warning(f"[WORKER REDIS] ✗ No agent configuration found for room {room_name}, using defaults")
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
    
    # Retrieve agent configuration from Redis
    logger.info(f"[WORKER ENTRYPOINT] Step 1: Retrieving agent configuration...")
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
        logger.warning(f"[WORKER TTS] No voice_id in config, will use default")
    
    # Create TTS with custom voice if specified
    if voice_id:
        try:
            logger.info(f"[WORKER TTS] Creating ElevenLabs TTS with custom voice_id={voice_id}...")
            tts = elevenlabs.TTS(
                voice_id=voice_id,
                model="eleven_turbo_v2_5",
                language=language_code,
                enable_ssml_parsing=False
            )
            logger.info(f"[WORKER TTS] ✓ SUCCESS: Created ElevenLabs TTS with voice_id={voice_id}, language={language_code}")
        except Exception as e:
            logger.error(f"[WORKER TTS] ✗ FAILED to create TTS with voice_id {voice_id}: {e}, using default")
            tts = elevenlabs.TTS(api_key=ELEVEN_API_KEY)
    else:
        logger.warning(f"[WORKER TTS] Using DEFAULT ElevenLabs TTS voice (no custom voice_id)")
        tts = elevenlabs.TTS(api_key=ELEVEN_API_KEY)
    
    # Create the agent session with all components
    session = AgentSession(
        stt=deepgram.STT(),
        llm=google.LLM(model="gemini-2.0-flash"),
        tts=tts,
        vad=silero.VAD.load(),
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
        logger.info("Chat History:")
        for item in session.history.items:
            if item.type == "message":
                safe_text = item.text_content.replace("\n", "\\n")
                text = f"{item.role}: {safe_text}"
                if item.interrupted:
                    text += " (interrupted)"
                logger.info(text)
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

