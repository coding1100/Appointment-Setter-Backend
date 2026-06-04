"""
LiveKit Voice Agent Worker
===========================
(UPDATED: Official Silero VAD + Turn Detector)

This worker connects to LiveKit and handles voice agent sessions for inbound telephony.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
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

# Hard upper bound on any single call. Even if the LLM ignores the prompt's
# "call end_call after the closing line" instruction, this watchdog guarantees
# the session is torn down so Twilio billing stops and worker capacity is
# released. Tune per traffic; 5 minutes covers a full appointment booking with
# headroom for slow speech / corrections.
MAX_CALL_DURATION_SECONDS = int(os.environ.get("VOICE_AGENT_MAX_CALL_DURATION", "300"))

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

    The Silero weights are baked into the image at build time
    (`download-files`), so this should complete in well under a second.
    If it stalls (e.g. CPU/memory starvation on the host), the worker's
    `initialize_process_timeout` will recycle this process. We time and
    guard the load so the failure is visible in logs rather than a silent
    10-minute hang (the production symptom seen on 2026-04-28).
    """
    import time

    logger.info("[VAD] Prewarming Silero VAD (once per worker process)")
    started = time.monotonic()
    try:
        proc.userdata["vad"] = silero.VAD.load(**VAD_SETTINGS)
    except Exception:
        logger.exception("[VAD] ✗ Failed to load Silero VAD during prewarm")
        # Re-raise so the supervisor recycles this process instead of
        # serving jobs without a VAD (which would crash every call).
        raise
    elapsed = time.monotonic() - started
    logger.info("[VAD] ✓ Silero VAD ready (%.2fs)", elapsed)


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
def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string (incl. 'Z') into a tz-aware UTC datetime.

    Raises ValueError with a clear message so the calling tool can return that
    message to the LLM, which then knows to ask the user for a clearer time.
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("empty datetime string")
    iso = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise ValueError(f"invalid ISO 8601 datetime: {value!r}") from exc
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class VoiceAgent(Agent):
    """Voice agent with the tools the prompt actually calls.

    Three tools are exposed to the LLM:
      * ``book_appointment`` — persist the booking and send confirmation
        emails. Call exactly once after the user has confirmed every field.
      * ``send_appointment_confirmation_email`` — direct email primitive
        (customer + owner). Also callable directly from tests/admin code.
      * ``end_call`` / ``close_session`` — terminate the session AFTER the
        LLM has spoken the closing line. Both names exist so existing prompts
        that reference ``close_session`` keep working; they share one impl.
    """

    def __init__(
        self,
        instructions: str,
        tenant_id: Optional[str],
        call_id: Optional[str] = None,
        job_ctx: Optional[agents.JobContext] = None,
    ):
        super().__init__(instructions=instructions)
        self.tenant_id = tenant_id
        self.call_id = call_id
        # JobContext is the official handle for ending a SIP call —
        # `job_ctx.api.room.delete_room(...)` disconnects the SIP participant
        # (Twilio's leg) and drops the caller's phone. session.aclose() does
        # NOT reliably terminate SIP, which is the production symptom we saw
        # ("speech not done in time after interruption", "entrypoint did not
        # exit in time"). Ref: https://docs.livekit.io/recipes/sip_lifecycle/
        self._job_ctx = job_ctx
        self._booking_completed = False  # idempotency guard for book_appointment

    # ------------------------------------------------------------------
    # Tool: book the appointment + send emails
    # ------------------------------------------------------------------
    @function_tool
    async def book_appointment(
        self,
        customer_name: str,
        customer_phone: str,
        customer_email: str,
        service_type: str,
        service_address: str,
        appointment_datetime: str,
        service_details: str = "",
    ) -> str:
        """Persist the appointment and send confirmation emails.

        Call this EXACTLY ONCE, after the caller has confirmed every field.
        `appointment_datetime` must be ISO 8601 (e.g. "2025-12-25T14:30:00Z").
        Returns a short status string for the LLM to react to: on success it
        instructs the LLM to deliver the closing line and call end_call; on
        failure it instructs the LLM to apologise and offer to retry.
        """
        if self._booking_completed:
            return (
                "Already booked. Deliver the closing line and call end_call."
            )
        if not self.tenant_id:
            logger.error("[BOOK] tenant_id missing on VoiceAgent; cannot book")
            return (
                "Booking failed: missing tenant context. Apologise to the "
                "caller and call end_call."
            )
        try:
            appointment_dt = _parse_iso_datetime(appointment_datetime)
        except ValueError as exc:
            logger.warning("[BOOK] Bad datetime from LLM: %s", exc)
            return (
                f"Booking failed: {exc}. Ask the caller to restate the date "
                "and time clearly."
            )

        from app.api.v1.services.appointment import appointment_service

        clean_email = (customer_email or "").strip() or None
        clean_name = customer_name.strip()
        clean_service = service_type.strip()
        clean_address = service_address.strip()
        clean_details = (service_details or "").strip() or None

        try:
            appointment = await appointment_service.create_appointment(
                tenant_id=self.tenant_id,
                customer_name=clean_name,
                customer_phone=customer_phone.strip(),
                customer_email=clean_email,
                service_type=clean_service,
                service_address=clean_address,
                appointment_datetime=appointment_dt,
                service_details=clean_details,
                call_id=self.call_id,
                # Own the email path so we can tell the LLM whether it
                # actually went out, instead of pretending success.
                send_email=False,
            )
        except Exception:
            logger.exception("[BOOK] create_appointment crashed")
            return (
                "Booking failed due to a system error. Apologise to the "
                "caller and call end_call."
            )

        if not appointment:
            # create_appointment returns None on validation/persistence errors;
            # it has already logged the cause.
            return (
                "Booking failed (the time may be unavailable). Offer the "
                "caller a different time or call end_call."
            )

        # Send the customer confirmation ourselves so we can read the
        # boolean status. `send_appointment_confirmation` catches its own
        # SMTP errors and returns False, logging the cause; we use that
        # signal to tell the LLM the truth instead of empty-promising an
        # email that never went out (common SMTP causes: MAIL_FROM domain
        # does not match the authenticated SMTP user — handled by the
        # Gmail-From defense in EmailService — or auth failure, or the
        # SMTP server unreachable). The booking still succeeds in the DB
        # regardless.
        customer_email_sent = False
        if clean_email:
            try:
                customer_email_sent = bool(
                    await appointment_service.email_service.send_appointment_confirmation(
                        clean_email,
                        clean_name,
                        appointment_dt,
                        clean_service,
                        clean_address,
                        appointment_id=appointment.get("id"),
                        service_details=clean_details,
                    )
                )
            except Exception:
                logger.exception("[BOOK] customer confirmation email send raised")

        # Owner notification is a courtesy email, not load-bearing for the
        # booking. Treat its failure as non-fatal — never let it sink the call.
        try:
            await self._notify_owner(
                customer_name=customer_name,
                customer_email=customer_email,
                appointment_datetime=appointment_dt,
                service_type=service_type,
                service_address=service_address,
            )
        except Exception as exc:
            logger.warning("[BOOK] Owner notification failed (non-fatal): %s", exc)

        self._booking_completed = True
        logger.info(
            "[BOOK] Created appointment id=%s tenant=%s call=%s customer_email_sent=%s",
            appointment.get("id"), self.tenant_id, self.call_id, customer_email_sent,
        )
        if customer_email_sent:
            return (
                "Appointment booked AND confirmation email sent. Call "
                "end_call with a closing_line that confirms the email is "
                "on its way."
            )
        return (
            "Appointment booked, BUT the confirmation email did NOT go "
            "out (SMTP failure — check backend logs). Call end_call with "
            "a closing_line that apologises briefly and says a teammate "
            "will follow up by phone. Do NOT promise an email."
        )

    # ------------------------------------------------------------------
    # Email primitive — used internally + directly by tests/admin code
    # ------------------------------------------------------------------
    async def send_appointment_confirmation_email(
        self,
        customer_email: str,
        customer_name: str,
        appointment_time: str,
        service_type: str,
        service_address: str,
    ) -> str:
        """Send the customer confirmation + the tenant-owner notification.

        Standalone primitive (no DB insert) — useful for retry/admin flows
        and exercised by `tests/test_voice_worker_email.py`. Returns the
        canonical success string for callers that need to detect success.
        """
        from app.services.email.service import EmailService
        from app.services.store import store

        appointment_dt = _parse_iso_datetime(appointment_time)

        owner_email = ""
        if self.tenant_id:
            tenant = await store.get_tenant(self.tenant_id)
            owner_email = (tenant or {}).get("owner_email") or ""

        email_service = EmailService()
        await email_service.send_appointment_confirmation(
            customer_email,
            customer_name,
            appointment_dt,
            service_type,
            service_address,
        )
        if owner_email:
            await email_service.send_appointment_owner_notification(
                owner_email,
                customer_name,
                customer_email,
                appointment_dt,
                service_type,
                service_address,
            )
        return "Appointment confirmation email sent successfully."

    async def _notify_owner(
        self,
        customer_name: str,
        customer_email: str,
        appointment_datetime: datetime,
        service_type: str,
        service_address: str,
    ) -> None:
        """Send the tenant-owner the new-booking notification, if configured."""
        from app.services.email.service import EmailService
        from app.services.store import store

        if not self.tenant_id:
            return
        tenant = await store.get_tenant(self.tenant_id)
        owner_email = (tenant or {}).get("owner_email")
        if not owner_email:
            return
        await EmailService().send_appointment_owner_notification(
            owner_email,
            customer_name,
            customer_email,
            appointment_datetime,
            service_type,
            service_address,
        )

    # ------------------------------------------------------------------
    # Tools: end the call cleanly — official LiveKit SIP recipe
    # ------------------------------------------------------------------
    # Sequence (per https://docs.livekit.io/recipes/sip_lifecycle/):
    #   1. session.say(closing_line)        — schedule the goodbye TTS
    #   2. await handle.wait_for_playout()  — block until audio fully drains
    #   3. job_ctx.api.room.delete_room(...) — disconnect SIP participant
    #
    # Why delete_room and not session.aclose():
    #   "Deleting the room disconnects all remote users, including SIP
    #    callers." — https://docs.livekit.io/agents/prebuilt/tools/end-call-tool/
    # session.aclose() is the agent's view of teardown and does not
    # reliably propagate SIP BYE to Twilio. The earlier production error
    # ("speech not done in time after interruption, cancelling the speech
    # arbitrarily") was the symptom of aclose() racing in-flight speech.
    DEFAULT_CLOSING_LINE = "Thanks for calling. Have a great day."

    async def _finish_call(self, closing_line: Optional[str] = None) -> str:
        logger.info(
            "[CALL] finishing call (tenant=%s call=%s)", self.tenant_id, self.call_id,
        )

        line = (closing_line or "").strip() or self.DEFAULT_CLOSING_LINE

        # Anti-double-goodbye:
        # The LLM sometimes emits a brief acknowledgement ("Great, thanks!")
        # in the same turn as end_call. That text is already being streamed
        # to TTS as `current_speech` by the time this tool runs. If we then
        # also call session.say(closing_line), the caller hears BOTH speeches
        # back-to-back ("Great, thanks!" + the closing line) and the call
        # sounds broken.
        #
        # Resolution: if a current speech exists, let it finish and use IT
        # as the goodbye — don't say a second one. Only when nothing is
        # in flight do we fall back to our deterministic closing line.
        current = self.session.current_speech
        if current is not None and not current.done:
            try:
                await asyncio.wait_for(current.wait_for_playout(), timeout=20.0)
                logger.info(
                    "[CALL] LLM-spoken closing drained; skipped tool say to avoid double goodbye",
                )
            except asyncio.TimeoutError:
                logger.warning("[CALL] LLM closing line timed out; interrupting and saying fallback")
                try:
                    current.interrupt()
                except Exception:
                    pass
                try:
                    handle = self.session.say(line)
                    await asyncio.wait_for(handle.wait_for_playout(), timeout=15.0)
                except Exception as exc:
                    logger.warning("[CALL] fallback say failed: %s", exc, exc_info=True)
        else:
            # No LLM-emitted speech — speak our deterministic goodbye.
            try:
                handle = self.session.say(line)
                try:
                    await asyncio.wait_for(handle.wait_for_playout(), timeout=20.0)
                except asyncio.TimeoutError:
                    logger.warning("[CALL] timed out (20s) waiting for closing line playout")
            except Exception as exc:
                logger.warning("[CALL] error speaking closing line: %s", exc, exc_info=True)

        # Step 3: hard hangup via room deletion — the only reliable way to
        # terminate the SIP participant. Falls back to aclose() only if the
        # job context isn't available.
        if self._job_ctx is not None:
            try:
                from livekit import api as lk_api

                await self._job_ctx.api.room.delete_room(
                    lk_api.DeleteRoomRequest(room=self._job_ctx.room.name)
                )
                logger.info(
                    "[CALL] room deleted; SIP participant disconnected (tenant=%s call=%s)",
                    self.tenant_id, self.call_id,
                )
                return "Call ended."
            except Exception as exc:
                logger.warning(
                    "[CALL] delete_room failed (%s); falling back to session.aclose()",
                    exc,
                )

        try:
            await self.session.aclose()
        except Exception as exc:
            logger.warning("[CALL] aclose() raised during finish: %s", exc)
        return "Call ended."

    @function_tool
    async def end_call(self, closing_line: str = "") -> str:
        """End the call after speaking a short closing line.

        Pass `closing_line` as the message you want the caller to hear
        before the line drops (e.g. "You're all set — a confirmation is
        on the way. Take care!"). If empty, a generic "Thanks for calling,
        have a great day." is spoken. The tool speaks the line, waits for
        it to finish playing, and then hangs up — do NOT speak it yourself
        first or the caller will hear it twice.

        Call exactly ONCE per call: after book_appointment succeeds, when
        the caller asks to hang up, or after retry discipline is exhausted.
        """
        return await self._finish_call(closing_line=closing_line)

    @function_tool
    async def close_session(self, closing_line: str = "") -> str:
        """Legacy alias for end_call. Either name works."""
        return await self._finish_call(closing_line=closing_line)


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

    # 5️⃣ Create agent + TTS. Pass the JobContext through so the agent can
    # call `ctx.api.room.delete_room(...)` for the official SIP hangup.
    agent = VoiceAgent(
        instructions=instructions,
        tenant_id=tenant_id,
        call_id=call_id,
        job_ctx=ctx,
    )
    tts = get_tts_service(config.get("voice_id"), "en")

    # 6️⃣ PREWARMED VAD (REQUIRED)
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        # prewarm_vad failed or never ran for this process. Fail loudly so
        # LiveKit recycles the process rather than crashing every turn.
        raise RuntimeError(
            "Silero VAD not available in process userdata — prewarm did not complete"
        )

    # =====================================================
    # ✅ AGENT SESSION (VAD + TURN DETECTOR)
    # =====================================================
    session = AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="en-US"),
        llm=google.LLM(model="gemini-2.5-flash-lite"),
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

    # Hard cap on call duration. Even if the LLM ignores the prompt and never
    # calls end_call, this guarantees the session is torn down so Twilio billing
    # stops, the agent slot is released, and we have a predictable upper bound
    # on call cost. The watchdog is cancelled when the session closes normally.
    async def _call_duration_watchdog() -> None:
        try:
            await asyncio.sleep(MAX_CALL_DURATION_SECONDS)
        except asyncio.CancelledError:
            return
        if closed_event.is_set():
            return
        logger.warning(
            "[CALL] Max duration %ss reached for tenant=%s call=%s — force-closing",
            MAX_CALL_DURATION_SECONDS, tenant_id, call_id,
        )
        try:
            await session.aclose()
        except Exception as exc:
            logger.warning("[CALL] aclose() during watchdog raised: %s", exc)

    watchdog_task = asyncio.create_task(_call_duration_watchdog())
    try:
        await closed_event.wait()
    finally:
        watchdog_task.cancel()
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
