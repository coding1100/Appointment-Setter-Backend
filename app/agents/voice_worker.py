"""
LiveKit Voice Agent Worker
===========================
(UPDATED: Official Silero VAD + Turn Detector)

This worker connects to LiveKit and handles voice agent sessions for inbound telephony.
"""

import asyncio
import json
import logging
from typing import Dict, Optional

from livekit import agents
from livekit.agents import Agent, AgentSession, function_tool, tts
from livekit.plugins import deepgram, google, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from app.core.async_redis import async_redis_client
from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
)
from app.core.prompts import get_template
from app.services.tts_provider import build_tts_with_fallback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgentWorker")

TTS_CACHE: Dict[str, tts.TTS] = {}
DEFAULT_TTS_CACHE_KEY = "__default__"
MAX_HISTORY_LOG_LINES = 40


# =========================================================
# ✅ OFFICIAL LIVEKIT VAD CONFIG (DO NOT USE 8kHz)
# =========================================================
VAD_SETTINGS = {
    "sample_rate": 16000,
    "min_speech_duration": 0.06,
    "min_silence_duration": 0.25,
    "prefix_padding_duration": 0.15,
    "activation_threshold": 0.5,
    "force_cpu": True,
}


def prewarm_vad(proc: agents.JobProcess):
    """
    Runs ONCE per worker process.
    This is the ONLY place Silero VAD should be loaded.
    """
    logger.info("[VAD] Prewarming Silero VAD (once per worker process)")
    proc.userdata["vad"] = silero.VAD.load(**VAD_SETTINGS)
    logger.info("[VAD] ✓ Silero VAD ready")


# =========================================================
# TTS CACHE
# =========================================================
def get_tts_service(voice_id: Optional[str], language_code: str) -> tts.TTS:
    cache_key = voice_id or DEFAULT_TTS_CACHE_KEY

    if cache_key in TTS_CACHE:
        return TTS_CACHE[cache_key]

    tts_service = build_tts_with_fallback(voice_id=voice_id, language_code=language_code)
    TTS_CACHE[cache_key] = tts_service
    return tts_service


# =========================================================
# AGENT
# =========================================================
class VoiceAgent(Agent):
    def __init__(self, instructions: str, tenant_id: Optional[str]):
        super().__init__(instructions=instructions)
        self.tenant_id = tenant_id
        self._closing_task: Optional[asyncio.Task] = None

    @function_tool
    async def close_session(self):
        await self.session.generate_reply(instructions="Say goodbye to the user.")
        await self.session.aclose()


# =========================================================
# ENTRYPOINT
# =========================================================
async def entrypoint(ctx: agents.JobContext):
    logger.info("=" * 80)
    logger.info("[WORKER ENTRYPOINT] Voice agent starting")
    logger.info(f"[WORKER ENTRYPOINT] Room: {ctx.room.name}")
    logger.info("=" * 80)

    # 1️⃣ Connect first
    await ctx.connect()
    await asyncio.sleep(0.5)

    # 2️⃣ Determine connection type: SIP (phone) or WebRTC (browser)
    sip_participant = None
    for p in ctx.room.remote_participants.values():
        if p.attributes:
            # Check if this is a SIP participant (has SIP attributes)
            attrs = p.attributes
            if attrs.get("lk_callid") or attrs.get("sip.h.x-lk-callid") or attrs.get("sip.twilio.callSid"):
                sip_participant = p
                break

    config = None
    tenant_id = None
    call_id = None

    if sip_participant:
        # ========================================
        # PHONE CALL MODE (SIP participant)
        # ========================================
        logger.info("[WORKER ENTRYPOINT] Detected SIP participant (phone call)")
        attrs = sip_participant.attributes
        original_call_sid = attrs.get("lk_callid") or attrs.get("sip.h.x-lk-callid") or attrs.get("sip.twilio.callSid")

        if not original_call_sid:
            raise RuntimeError("Missing CallSid in SIP attributes")

        logger.info(f"[WORKER ENTRYPOINT] CallSid: {original_call_sid}")

        # Load config from Redis by CallSid
        config = await async_redis_client.get(f"call_config:{original_call_sid}")
        if not config:
            raise RuntimeError(f"No config found for CallSid {original_call_sid}")

        config = json.loads(config)
        tenant_id = config.get("tenant_id")
        call_id = config.get("call_id")
        logger.info(f"[WORKER ENTRYPOINT] Loaded config for tenant: {tenant_id}, call_id: {call_id}")

    else:
        # ========================================
        # BROWSER TEST MODE (WebRTC participant)
        # ========================================
        logger.info("[WORKER ENTRYPOINT] Detected WebRTC participant (browser test)")
        
        # Browser test rooms: config is stored by room name
        room_name = ctx.room.name
        config_key = f"room_config:{room_name}"
        logger.info(f"[WORKER ENTRYPOINT] Looking up config for room: {room_name}")
        
        config = await async_redis_client.get(config_key)
        if not config:
            raise RuntimeError(f"No config found for browser test room: {room_name}")
        
        config = json.loads(config)
        tenant_id = config.get("tenant_id")
        call_id = config.get("call_id") or config.get("session_id")
        logger.info(f"[WORKER ENTRYPOINT] Loaded browser test config for tenant: {tenant_id}, call_id: {call_id}")

    # 4️⃣ Build instructions
    instructions = get_template(
        service_type=config.get("service_type", "Home Services"),
        agent_name=config.get("agent_data", {}).get("name", "Assistant"),
    )

    greeting = config.get("agent_data", {}).get("greeting_message")

    # 5️⃣ Create agent + TTS
    agent = VoiceAgent(instructions=instructions, tenant_id=tenant_id)
    tts = get_tts_service(config.get("voice_id"), "en")

    # 6️⃣ PREWARMED VAD (REQUIRED)
    vad = ctx.proc.userdata["vad"]

    # =====================================================
    # ✅ AGENT SESSION (VAD + TURN DETECTOR)
    # =====================================================
    session = AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="en-US"),
        llm=google.LLM(model="gemini-2.0-flash"),
        tts=tts,
        vad=vad,

        # 🔥 LiveKit Turn Detector (official recommendation)
        turn_detection=MultilingualModel(),

        # Endpointing tuned for telephony
        min_endpointing_delay=0.35,
        max_endpointing_delay=2.5,

        allow_interruptions=True,
        min_interruption_duration=0.35,
    )

    await session.start(room=ctx.room, agent=agent)
    logger.info("[WORKER ENTRYPOINT] ✓ Agent session started")

    # 7️⃣ Initial greeting
    if greeting:
        await session.generate_reply(
            instructions=f"Greet the user by saying exactly: '{greeting}'"
        )
    else:
        await session.generate_reply()

    closed_event = asyncio.Event()

    @session.on("close")
    def on_close(_):
        async def cleanup():
            try:
                # Clean up both tenant_config and room_config
                await async_redis_client.delete(f"tenant_config:{tenant_id}:{call_id}")
                await async_redis_client.delete(f"room_config:{ctx.room.name}")
                logger.info("[CLEANUP] Deleted per-call configs")
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed: {e}")
            closed_event.set()

        asyncio.create_task(cleanup())

    await closed_event.wait()
    logger.info(f"[WORKER ENTRYPOINT] Call completed for tenant {tenant_id}")


# =========================================================
# WORKER BOOTSTRAP
# =========================================================
if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()

    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm_vad,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
            ws_url=LIVEKIT_URL,
            agent_name="voice-agent",
        )
    )
