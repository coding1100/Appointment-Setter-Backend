"""
Unified LiveKit Voice Agent Service
Handles both browser-based testing and Twilio phone call integration.
Single service for all voice agent interactions.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm, stt, tts
from livekit.agents.voice.agent import Agent
from livekit.plugins import google, deepgram, elevenlabs, silero
from livekit.plugins.elevenlabs import tts as elevenlabs_tts
from livekit import api
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial

from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    LIVEKIT_SIP_DOMAIN,
    GOOGLE_API_KEY,
    DEEPGRAM_API_KEY,
    ELEVEN_API_KEY,
    TWILIO_WEBHOOK_BASE_URL,
)
from app.services.dialog_manager import dialog_manager
from app.services.firebase import firebase_service
from app.core.encryption import encryption_service
from app.core.async_redis import async_redis_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedVoiceAgentService:
    """
    Unified voice agent service that handles both:
    1. Browser-based testing (direct LiveKit connection)
    2. Phone calls (Twilio SIP → LiveKit bridge)

    Each tenant gets their own agent instance that serves both modes.
    """

    def __init__(self):
        """Initialize unified voice agent service."""
        self.tenant_agents = {}  # tenant_id:service_type -> agent_instance
        self.active_sessions = {}  # session_id -> session_data
        self._livekit_api = None

        # Validate LiveKit configuration at startup
        self._validate_livekit_config()

    def _validate_livekit_config(self):
        """Validate LiveKit configuration at startup."""
        logger.info("=" * 60)
        logger.info("VALIDATING LIVEKIT CONFIGURATION")
        logger.info("=" * 60)
        logger.info(f"LIVEKIT_URL: '{LIVEKIT_URL}'")
        logger.info(f"LIVEKIT_API_KEY: {'✓ SET' if LIVEKIT_API_KEY else '✗ NOT SET'}")
        logger.info(f"LIVEKIT_API_SECRET: {'✓ SET' if LIVEKIT_API_SECRET else '✗ NOT SET'}")

        if not LIVEKIT_URL or LIVEKIT_URL.strip() == "":
            logger.error("⚠️ CRITICAL: LIVEKIT_URL is not configured!")
            logger.error("Please set LIVEKIT_URL in your .env file")
        else:
            logger.info(f"✓ LIVEKIT_URL is configured")

        logger.info("=" * 60)

    @property
    def livekit_api(self):
        """Get LiveKit API instance (lazy initialization)."""
        if self._livekit_api is None:
            if not LIVEKIT_URL:
                raise ValueError("LIVEKIT_URL is not configured")
            self._livekit_api = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        return self._livekit_api

    def _get_agent_key(self, tenant_id: str, service_type: str) -> str:
        """Generate agent key for tenant and service type."""
        return f"{tenant_id}:{service_type}"

    async def get_or_create_agent(
        self,
        tenant_id: str,
        service_type: str,
        voice_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ) -> Agent:
        """
        Get existing agent instance or create new one for tenant.
        Each tenant has one agent per service type.

        Args:
            tenant_id: Tenant identifier
            service_type: Service type (e.g., "Plumbing")
            voice_id: Optional ElevenLabs voice ID to use
            agent_id: Optional agent ID (used to create unique key per agent)
            agent_config: Optional full agent configuration (includes greeting, language, etc.)
        """
        # Use agent_id in key if provided for agent-specific instances
        agent_key = self._get_agent_key(tenant_id, service_type)
        if agent_id:
            agent_key = f"{agent_key}:{agent_id}"

        # Check if agent exists and if voice_id has changed
        should_recreate = False
        if agent_key in self.tenant_agents:
            cached_voice_id = self.tenant_agents[agent_key].get("voice_id")
            if cached_voice_id != voice_id:
                logger.info(f"Voice changed from {cached_voice_id} to {voice_id}, recreating agent")
                should_recreate = True

        if agent_key not in self.tenant_agents or should_recreate:
            logger.info(f"Creating new agent for {agent_key} with voice_id={voice_id} (this may take 5-10 seconds...)")

            # Get tenant-specific configuration
            tenant_config = await self._get_tenant_config(tenant_id)

            # Create agent with tenant-specific settings
            # Using Gemini for LLM, Deepgram for STT, ElevenLabs for TTS
            system_prompt = self._get_system_prompt(tenant_config, service_type, agent_config)

            # Configure ElevenLabs TTS with voice_id if provided
            # Version 1.2.15 signature: TTS(voice_id: str, model: str, language: str, ...)
            if voice_id:
                try:
                    # Extract language code (en-US -> en)
                    language_code = "en"
                    if agent_config and "language" in agent_config:
                        language_code = agent_config.get("language", "en-US").split("-")[0]

                    tts_service = elevenlabs.TTS(
                        voice_id=voice_id, model="eleven_turbo_v2_5", language=language_code, enable_ssml_parsing=False
                    )

                    agent_name = agent_config.get("name", "Agent") if agent_config else "Agent"
                    logger.info(
                        f"✓ SUCCESS: Created ElevenLabs TTS with voice_id={voice_id} (Emily voice), model=eleven_turbo_v2_5, language={language_code}, agent={agent_name}"
                    )

                except Exception as e:
                    logger.error(f"✗ FAILED to create TTS with voice_id: {e}")
                    logger.warning("Falling back to default voice")
                    tts_service = elevenlabs.TTS()
            else:
                # No voice_id provided
                logger.warning("No voice_id provided, using default ElevenLabs voice (bIHbv24MWmeRgasZH58o)")
                tts_service = elevenlabs.TTS()

            # Create the agent with instructions parameter (LiveKit 1.0 API)
            agent = Agent(
                vad=silero.VAD.load(),
                stt=deepgram.STT(),
                llm=google.LLM(model="gemini-2.0-flash"),
                tts=tts_service,
                instructions=system_prompt,  # System instructions for the agent
            )

            self.tenant_agents[agent_key] = {
                "agent": agent,
                "created_at": datetime.now(timezone.utc),
                "tenant_id": tenant_id,
                "service_type": service_type,
                "voice_id": voice_id,
                "agent_id": agent_id,
            }

            logger.info(f"✓ Agent instance created and cached successfully")
        else:
            logger.info(f"✓ Using cached agent instance")

        return self.tenant_agents[agent_key]["agent"]

    async def start_session(
        self,
        tenant_id: str,
        service_type: str,
        test_mode: bool = True,
        phone_number: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Start a voice agent session.

        Args:
            tenant_id: Tenant identifier
            service_type: Type of service (e.g., "Plumbing", "Electrician")
            test_mode: If True, returns token for browser testing. If False, initiates phone call.
            phone_number: Required if test_mode=False. Customer's phone number.
            metadata: Additional session metadata (can include agent_id)

        Returns:
            Session data with room info and connection details
        """
        try:
            session_id = str(uuid.uuid4())
            room_name = f"agent-{tenant_id}-{session_id}"

            logger.info(f"Starting session {session_id} for tenant {tenant_id}, test_mode={test_mode}, metadata={metadata}")

            # Extract agent_id from metadata if provided
            agent_id = None
            voice_id = None
            agent_data = None

            if metadata and "agent_id" in metadata:
                agent_id = metadata["agent_id"]
                logger.info(f"Using agent_id from metadata: {agent_id}")

                # Fetch agent details from database to get voice_id and other settings
                try:
                    agent_data = await firebase_service.get_agent(agent_id)
                    if agent_data:
                        voice_id = agent_data.get("voice_id")
                        logger.info(
                            f"Fetched agent config - voice_id: {voice_id}, name: {agent_data.get('name')}, language: {agent_data.get('language')}"
                        )
                    else:
                        logger.warning(f"Agent {agent_id} not found in database")
                except Exception as e:
                    logger.error(f"Error fetching agent data: {e}")

            # Get or create agent instance for this tenant with specific voice
            # This can be slow on first creation, so we ensure it completes
            logger.info(f"Getting or creating agent instance (may take a moment on first creation)...")
            agent = await self.get_or_create_agent(
                tenant_id=tenant_id, service_type=service_type, voice_id=voice_id, agent_id=agent_id, agent_config=agent_data
            )
            logger.info(f"Agent instance ready")

            # Create LiveKit room and store agent configuration for worker to use
            logger.info(f"Creating LiveKit room: {room_name}")

            # Clean agent_data for JSON serialization (remove non-serializable fields)
            clean_agent_data = None
            if agent_data:
                clean_agent_data = {
                    "id": agent_data.get("id"),
                    "name": agent_data.get("name"),
                    "voice_id": agent_data.get("voice_id"),
                    "language": agent_data.get("language"),
                    "greeting_message": agent_data.get("greeting_message"),
                    "service_type": agent_data.get("service_type"),
                    "tenant_id": agent_data.get("tenant_id"),
                }
                logger.info(f"Cleaned agent data for storage: {clean_agent_data}")

            room_config = {
                "tenant_id": tenant_id,
                "service_type": service_type,
                "agent_id": agent_id,
                "voice_id": voice_id,
                "agent_data": clean_agent_data,
            }
            logger.info(f"Room config to store: {room_config}")
            await self._create_room(room_name, room_config)
            logger.info(f"LiveKit room created successfully")

            # Create dialog context
            dialog_context = await dialog_manager.create_dialog_context(
                tenant_id=tenant_id, call_id=session_id, service_type=service_type
            )

            # Store session data
            session_data = {
                "session_id": session_id,
                "tenant_id": tenant_id,
                "service_type": service_type,
                "room_name": room_name,
                "test_mode": test_mode,
                "phone_number": phone_number,
                "status": "initializing",
                "dialog_context": dialog_context,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": None,
                "ended_at": None,
            }

            if test_mode:
                # Browser testing mode: Generate token for direct LiveKit connection
                token = self._generate_room_token(room_name, f"client-{session_id}")
                session_data["status"] = "ready"
                session_data["connection_type"] = "browser"

                # Format LiveKit URL properly with extensive validation
                livekit_url = LIVEKIT_URL
                logger.info(f"Raw LIVEKIT_URL from config: '{livekit_url}'")

                if not livekit_url or livekit_url.strip() == "":
                    logger.error("LIVEKIT_URL is not configured or empty!")
                    raise ValueError("LIVEKIT_URL is not configured in environment variables")

                # Clean the URL
                livekit_url = livekit_url.strip()
                livekit_url = livekit_url.rstrip("/")

                # Ensure proper protocol
                if not livekit_url.startswith(("ws://", "wss://")):
                    # If it has http/https, convert to ws/wss
                    if livekit_url.startswith("https://"):
                        livekit_url = livekit_url.replace("https://", "wss://", 1)
                    elif livekit_url.startswith("http://"):
                        livekit_url = livekit_url.replace("http://", "ws://", 1)
                    else:
                        # No protocol, add wss
                        livekit_url = f"wss://{livekit_url}"

                logger.info(f"Formatted LIVEKIT_URL: '{livekit_url}'")

                # Validate the URL is properly formed
                if not livekit_url or livekit_url in ["wss://", "ws://"]:
                    logger.error(f"Invalid formatted URL: '{livekit_url}'")
                    raise ValueError("LIVEKIT_URL resulted in invalid format after processing")

                result = {
                    "session_id": session_id,
                    "room_name": room_name,
                    "token": token,
                    "livekit_url": livekit_url,
                    "status": "ready",
                    "message": "Connect your browser to the LiveKit room using the provided token",
                }
            else:
                # Phone call mode: Initiate Twilio call → LiveKit bridge
                if not phone_number:
                    raise ValueError("phone_number is required when test_mode=False")

                call_sid = await self._initiate_twilio_call(
                    tenant_id=tenant_id, phone_number=phone_number, room_name=room_name
                )

                session_data["status"] = "calling"
                session_data["connection_type"] = "phone"
                session_data["twilio_call_sid"] = call_sid

                result = {
                    "session_id": session_id,
                    "room_name": room_name,
                    "status": "calling",
                    "twilio_call_sid": call_sid,
                    "phone_number": phone_number,
                    "message": f"Calling {phone_number}...",
                }

            self.active_sessions[session_id] = session_data

            return result

        except Exception as e:
            logger.error(f"Error starting session: {e}")
            raise Exception(f"Failed to start session: {str(e)}")

    async def end_session(self, session_id: str) -> bool:
        """End a voice agent session."""
        try:
            if session_id not in self.active_sessions:
                logger.warning(f"Session {session_id} not found")
                return False

            session = self.active_sessions[session_id]
            room_name = session["room_name"]

            logger.info(f"Ending session {session_id}")

            # Update session status
            session["status"] = "ended"
            session["ended_at"] = datetime.now(timezone.utc).isoformat()

            # Delete LiveKit room
            await self._delete_room(room_name)

            # If it's a phone call, hang up Twilio call
            if not session["test_mode"] and "twilio_call_sid" in session:
                await self._hangup_twilio_call(session["tenant_id"], session["twilio_call_sid"])

            # Clean up
            del self.active_sessions[session_id]

            return True

        except Exception as e:
            logger.error(f"Error ending session: {e}")
            return False

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session status."""
        return self.active_sessions.get(session_id)

    async def clear_agent_cache(self, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear cached agent instances.

        Args:
            tenant_id: If provided, clear only agents for this tenant
            agent_id: If provided, clear only this specific agent

        Returns:
            Dictionary with count of cleared agents
        """
        cleared = 0

        if agent_id and tenant_id:
            # Clear specific agent
            keys_to_remove = [key for key in self.tenant_agents.keys() if agent_id in key and tenant_id in key]
        elif tenant_id:
            # Clear all agents for tenant
            keys_to_remove = [key for key in self.tenant_agents.keys() if tenant_id in key]
        else:
            # Clear all agents
            keys_to_remove = list(self.tenant_agents.keys())

        for key in keys_to_remove:
            del self.tenant_agents[key]
            cleared += 1

        logger.info(f"Cleared {cleared} agent instance(s) from cache")
        return {"cleared": cleared, "message": f"Successfully cleared {cleared} agent instance(s)"}

    async def handle_twilio_webhook(self, form_data: Dict[str, Any]) -> VoiceResponse:
        """
        Handle incoming Twilio webhook.
        This is called when a Twilio call is initiated (inbound or outbound).
        Returns TwiML that connects the call to LiveKit via SIP.

        Supports two scenarios:
        1. OUTBOUND: Backend initiates call -> session exists -> use existing room
        2. INBOUND: Customer calls Twilio number -> no session -> lookup agent by phone number
        """
        try:
            # Extract call information
            call_sid = form_data.get("CallSid")
            from_number = form_data.get("From")
            to_number = form_data.get("To")

            logger.info(f"Twilio webhook: CallSid={call_sid}, From={from_number}, To={to_number}")

            # Find the session associated with this call (OUTBOUND scenario)
            session = None
            for sess_id, sess_data in self.active_sessions.items():
                if sess_data.get("twilio_call_sid") == call_sid:
                    session = sess_data
                    break

            if session:
                # OUTBOUND CALL: Use existing session
                logger.info(f"Found existing session for outbound call {call_sid}")
                room_name = session["room_name"]
            else:
                # INBOUND CALL: Lookup agent by phone number
                logger.info(f"No existing session, treating as INBOUND call to {to_number}")

                # Lookup phone number assignment in database
                phone_record = await firebase_service.get_phone_by_number(to_number)

                if not phone_record:
                    logger.error(f"Phone number {to_number} not found in database")
                    response = VoiceResponse()
                    response.say("This number is not configured. Please contact support.")
                    response.hangup()
                    return response

                if not phone_record.get("agent_id"):
                    logger.error(f"Phone number {to_number} has no agent assigned")
                    response = VoiceResponse()
                    response.say("This number is not assigned to an agent. Please contact support.")
                    response.hangup()
                    return response

                agent_id = phone_record["agent_id"]
                tenant_id = phone_record["tenant_id"]

                # Get agent configuration
                agent = await firebase_service.get_agent(agent_id)
                if not agent:
                    logger.error(f"Agent {agent_id} not found in database")
                    response = VoiceResponse()
                    response.say("Agent configuration not found. Please contact support.")
                    response.hangup()
                    return response

                # Create LiveKit room for inbound call
                # Match LiveKit dispatch rule pattern: inbound-<caller-number>
                # Use caller number + call_sid for uniqueness (to avoid conflicts if same caller calls multiple times)
                caller_number_clean = from_number.replace("+", "").replace("-", "").replace(" ", "")
                # Use format: inbound-{caller_number}-{short_call_sid} to ensure uniqueness
                # This matches dispatch rule prefix 'inbound-' while keeping each call unique
                room_name = f"inbound-{caller_number_clean}-{call_sid[-8:]}"  # Last 8 chars of call_sid for uniqueness
                logger.info(f"Creating LiveKit room {room_name} for inbound call")

                # Prepare agent config for Redis (worker will pick this up)
                config_data = {
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "agent_data": agent,
                    "voice_id": agent.get("voice_id"),
                    "service_type": agent.get("service_type", "Home Services"),
                    "call_type": "inbound",
                    "caller_number": from_number,
                    "called_number": to_number,
                }

                # Create room and store config in Redis
                # Note: Room must exist and be ready before Twilio can connect via SIP
                room_created = await self._create_room(room_name, config_data)

                if not room_created:
                    logger.error(f"Failed to create LiveKit room {room_name}")
                    response = VoiceResponse()
                    response.say("Unable to connect the call. Please try again later.")
                    response.hangup()
                    return response

                # Verify room exists and is ready (critical for SIP connections)
                room_verified = await self._verify_room_exists(room_name)
                if not room_verified:
                    logger.warning(f"Room {room_name} created but verification failed. Continuing anyway...")
                    # Don't fail here - room might be ready but not yet in list
                    # LiveKit sometimes has a small delay in room availability

                logger.info(f"✓ Created LiveKit room {room_name} and stored agent config")
                logger.info(
                    f"Agent: {agent.get('name')}, Service: {agent.get('service_type')}, Voice: {agent.get('voice_id')}"
                )

                # Track inbound call session
                self.active_sessions[call_sid] = {
                    "session_id": call_sid,
                    "room_name": room_name,
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "twilio_call_sid": call_sid,
                    "status": "connecting",
                    "call_type": "inbound",
                    "from_number": from_number,
                    "to_number": to_number,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                logger.info(f"✓ Inbound call setup complete for {to_number} -> Agent {agent.get('name')}")

            # For inbound calls: Use TwiML <Dial><SIP> to route to LiveKit
            # The SIP URI format: sip:room_name@livekit_sip_domain
            # LiveKit will automatically create the SIP participant when the call arrives
            sip_uri = self._get_livekit_sip_uri(room_name)

            logger.info(f"Routing call to LiveKit with SIP URI: {sip_uri}")
            logger.info(f"Room: {room_name}, Agent: {agent.get('name')}")

            # Create TwiML response that dials into LiveKit room
            response = VoiceResponse()
            dial = Dial()
            dial.sip(sip_uri)
            response.append(dial)

            # Update session status
            if session:
                session["status"] = "connecting"
                session["started_at"] = datetime.now(timezone.utc).isoformat()
            else:
                self.active_sessions[call_sid]["status"] = "connecting"
                self.active_sessions[call_sid]["started_at"] = datetime.now(timezone.utc).isoformat()

            return response

        except Exception as e:
            logger.error(f"Error in Twilio webhook: {e}", exc_info=True)
            response = VoiceResponse()
            response.say("An error occurred. Please try again later.")
            response.hangup()
            return response

    async def handle_twilio_status_callback(self, form_data: Dict[str, Any]):
        """Handle Twilio call status updates."""
        try:
            call_sid = form_data.get("CallSid")
            call_status = form_data.get("CallStatus")

            logger.info(f"Twilio status: CallSid={call_sid}, Status={call_status}")

            # Find and update session
            for session in self.active_sessions.values():
                if session.get("twilio_call_sid") == call_sid:
                    session["twilio_status"] = call_status

                    if call_status in ["completed", "failed", "busy", "no-answer"]:
                        session["status"] = "ended"
                        session["ended_at"] = datetime.now(timezone.utc).isoformat()

                    break

        except Exception as e:
            logger.error(f"Error in status callback: {e}")

    # Private helper methods

    async def _get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant configuration from Firebase."""
        try:
            config = await firebase_service.get_agent_settings(tenant_id)
            return config or {}
        except Exception as e:
            logger.warning(f"Failed to get tenant config from Firebase: {e}")
            logger.info("Using default configuration")
            return {"business_name": "our company", "service_type": "Home Services"}

    def _get_system_prompt(
        self, tenant_config: Dict[str, Any], service_type: str, agent_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate system prompt for the agent."""
        business_name = tenant_config.get("business_name", "our company")

        # Use agent's custom greeting if available
        if agent_config:
            agent_name = agent_config.get("name", "Agent")
            greeting = agent_config.get("greeting_message", "")
            language = agent_config.get("language", "en-US")

            logger.info(f"Using custom agent config - Name: {agent_name}, Language: {language}, Greeting: {greeting[:50]}...")

            return f"""You are {agent_name}, a professional appointment booking assistant for {business_name}, specializing in {service_type} services.

Your greeting: "{greeting}"

Your role is to help customers schedule appointments by collecting:
- Customer name
- Phone number
- Email address
- Service address
- Preferred date and time
- Service details and requirements

Be friendly, professional, and efficient. Confirm all details before booking the appointment.
If you need to escalate to a human, politely explain that you're transferring them to a representative.

Current service type: {service_type}
Business: {business_name}
Language: {language}"""
        else:
            return f"""You are a professional appointment booking assistant for {business_name}, specializing in {service_type} services.

Your role is to help customers schedule appointments by collecting:
- Customer name
- Phone number
- Email address
- Service address
- Preferred date and time
- Service details and requirements

Be friendly, professional, and efficient. Confirm all details before booking the appointment.
If you need to escalate to a human, politely explain that you're transferring them to a representative.

Current service type: {service_type}
Business: {business_name}"""

    async def _create_room(self, room_name: str, room_config: Optional[Dict[str, Any]] = None) -> bool:
        """Create a LiveKit room and store configuration for worker."""
        try:
            await self.livekit_api.room.create_room(
                api.CreateRoomRequest(name=room_name, empty_timeout=300, max_participants=10)  # 5 minutes
            )
            logger.info(f"Created LiveKit room: {room_name}")

            # Store room configuration in Redis for worker to retrieve
            if room_config:
                import json

                config_key = f"livekit:room_config:{room_name}"
                config_json = json.dumps(room_config)
                logger.info(f"[REDIS STORE] Storing config in Redis with key: {config_key}")
                logger.info(f"[REDIS STORE] Config JSON: {config_json}")
                await async_redis_client.set(config_key, config_json, ttl=3600)  # Expire in 1 hour
                logger.info(f"[REDIS STORE] ✓ Successfully stored room configuration in Redis for room: {room_name}")

                # Verify storage by reading back
                verify_data = await async_redis_client.get(config_key)
                if verify_data:
                    logger.info(f"[REDIS VERIFY] ✓ Configuration verified in Redis: {verify_data}")
                else:
                    logger.error(f"[REDIS VERIFY] ✗ Failed to verify configuration in Redis!")

            return True
        except Exception as e:
            logger.error(f"Error creating room: {e}")
            return False

    async def _delete_room(self, room_name: str) -> bool:
        """Delete a LiveKit room and clean up configuration."""
        try:
            await self.livekit_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"Deleted LiveKit room: {room_name}")

            # Clean up room configuration from Redis
            config_key = f"livekit:room_config:{room_name}"
            await async_redis_client.delete(config_key)
            logger.info(f"Cleaned up room configuration from Redis for room: {room_name}")

            return True
        except Exception as e:
            logger.error(f"Error deleting room: {e}")
            return False

    def _generate_room_token(self, room_name: str, identity: str) -> str:
        """Generate a LiveKit room token."""
        try:
            token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            token.with_identity(identity)
            token.with_name("Voice Agent Client")
            token.with_grants(
                api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True, can_publish_data=True)
            )
            return token.to_jwt()
        except Exception as e:
            logger.error(f"Error generating token: {e}")
            raise

    async def _initiate_twilio_call(self, tenant_id: str, phone_number: str, room_name: str) -> str:
        """Initiate a Twilio phone call that will connect to LiveKit room."""
        try:
            # Get tenant's Twilio credentials with decrypted auth_token
            twilio_integration = await firebase_service.get_twilio_integration(tenant_id)
            if twilio_integration and "auth_token" in twilio_integration:
                try:
                    twilio_integration["auth_token"] = encryption_service.decrypt(twilio_integration["auth_token"])
                except Exception as e:
                    logger.error(f"Failed to decrypt auth_token: {e}")
                    raise

            if not twilio_integration:
                raise ValueError(f"No Twilio integration found for tenant {tenant_id}")

            # Create Twilio client with tenant's credentials
            twilio_client = Client(twilio_integration["account_sid"], twilio_integration["auth_token"])

            # Webhook URL that will return TwiML to connect to LiveKit
            webhook_url = f"{TWILIO_WEBHOOK_BASE_URL}/api/v1/voice-agent/twilio/webhook"

            # Initiate call
            call = twilio_client.calls.create(
                from_=twilio_integration["phone_number"],
                to=phone_number,
                url=webhook_url,
                status_callback=f"{TWILIO_WEBHOOK_BASE_URL}/api/v1/voice-agent/twilio/status",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
            )

            logger.info(f"Initiated Twilio call: {call.sid}")
            return call.sid

        except Exception as e:
            logger.error(f"Error initiating Twilio call: {e}")
            raise

    async def _hangup_twilio_call(self, tenant_id: str, call_sid: str):
        """Hang up a Twilio call."""
        try:
            twilio_integration = await firebase_service.get_twilio_integration(tenant_id)
            if twilio_integration and "auth_token" in twilio_integration:
                try:
                    twilio_integration["auth_token"] = encryption_service.decrypt(twilio_integration["auth_token"])
                except Exception as e:
                    logger.error(f"Failed to decrypt auth_token: {e}")
                    return
            if twilio_integration:
                twilio_client = Client(twilio_integration["account_sid"], twilio_integration["auth_token"])
                twilio_client.calls(call_sid).update(status="completed")
                logger.info(f"Hung up Twilio call: {call_sid}")
        except Exception as e:
            logger.error(f"Error hanging up call: {e}")

    async def _verify_room_exists(self, room_name: str) -> bool:
        """Verify that a LiveKit room exists and is ready."""
        try:
            room_info = await self.livekit_api.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
            if room_info.rooms and len(room_info.rooms) > 0:
                room = room_info.rooms[0]
                logger.info(f"✓ Room {room_name} exists and is ready (num_participants={room.num_participants})")
                return True
            else:
                logger.warning(f"Room {room_name} not found in LiveKit")
                return False
        except Exception as e:
            logger.error(f"Error verifying room {room_name}: {e}")
            return False

    def _get_livekit_sip_uri(self, room_name: str) -> str:
        """
        Generate SIP URI for routing inbound Twilio calls to LiveKit room.

        Format: sip:room_name@livekit_sip_domain

        IMPORTANT:
        - LiveKit SIP domain must be configured in LIVEKIT_SIP_DOMAIN
        - The room name in the SIP URI tells LiveKit which room to route the call to
        - LiveKit will automatically create a SIP participant when the call arrives
        - The agent worker will pick up the call based on the room config in Redis

        Example: sip:inbound-CA123456@3nbu801ppzl.sip.livekit.cloud

        Note: This is for INBOUND calls only. For outbound calls, use CreateSIPParticipant API.
        """
        # Validate room_name
        if not room_name or not room_name.strip():
            logger.error(f"Invalid room_name provided to _get_livekit_sip_uri: '{room_name}'")
            raise ValueError(f"room_name cannot be empty. Received: '{room_name}'")

        room_name = room_name.strip()

        if not LIVEKIT_SIP_DOMAIN:
            logger.error("LIVEKIT_SIP_DOMAIN not configured. Cannot generate SIP URI.")
            raise ValueError(
                "LIVEKIT_SIP_DOMAIN must be configured. "
                "Get your SIP domain from LiveKit Cloud dashboard → SIP → Inbound Trunks."
            )

        domain = LIVEKIT_SIP_DOMAIN.strip()
        # Remove any 'sip:' prefix if accidentally included
        if domain.startswith("sip:"):
            domain = domain[4:]

        # Validate domain format
        if not domain or "@" in domain:
            logger.error(
                f"Invalid SIP domain format: '{domain}'. Should be just the domain (e.g., '3nbu801ppzl.sip.livekit.cloud')"
            )
            raise ValueError(f"Invalid SIP domain format: '{domain}'. Domain should not include 'sip:' prefix or '@' symbol.")

        # Standard format: sip:room_name@domain
        sip_uri = f"sip:{room_name}@{domain}"

        logger.info(f"Generated SIP URI: {sip_uri} (room_name='{room_name}', domain='{domain}')")
        return sip_uri


# Global instance
unified_voice_agent_service = UnifiedVoiceAgentService()
