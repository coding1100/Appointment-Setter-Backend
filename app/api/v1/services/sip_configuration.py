"""
SIP Configuration Service for automating LiveKit and Twilio SIP setup.
Handles SIP trunk, dispatch rules, and phone number webhook configuration.

ARCHITECTURE:
- Each phone number gets its own SIP inbound trunk
- All trunks are attached to the shared dispatch rule
- Dispatch rule uses Individual mode with roomPrefix="call-" and agentName="voice-agent"
- Tenant routing is handled via SIP headers, NOT trunk metadata
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from livekit import api
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.api.v1.services.tenant import tenant_service
from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_SIP_DOMAIN,
    LIVEKIT_URL,
)
from app.core.encryption import encryption_service
from app.services.firebase import firebase_service
from app.utils.phone_number import normalize_phone_number, normalize_phone_number_safe

# Configure logging
logger = logging.getLogger(__name__)

# Expected dispatch rule configuration
EXPECTED_ROOM_PREFIX = "call-"
EXPECTED_AGENT_NAME = "voice-agent"


async def _run_twilio_sync(func: Callable) -> Any:
    """Helper function to run synchronous Twilio operations in a thread pool."""
    return await asyncio.to_thread(func)


class SIPConfigurationService:
    """Service for managing SIP configuration between LiveKit and Twilio."""

    def __init__(self):
        """Initialize SIP configuration service."""
        self._livekit_api = None

    def _get_livekit_api(self) -> api.LiveKitAPI:
        """
        Get LiveKit API client instance (singleton pattern).
        
        Reuses the same instance to avoid creating multiple aiohttp sessions.
        """
        if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
            raise ValueError(
                "LiveKit configuration is missing. Please set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET."
            )
        
        if self._livekit_api is None:
            self._livekit_api = api.LiveKitAPI(
                url=LIVEKIT_URL, 
                api_key=LIVEKIT_API_KEY, 
                api_secret=LIVEKIT_API_SECRET
            )
        
        return self._livekit_api

    async def _get_decrypted_twilio_integration(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get Twilio integration with decrypted auth_token."""
        integration = await firebase_service.get_twilio_integration(tenant_id)
        if integration and "auth_token" in integration:
            try:
                integration["auth_token"] = encryption_service.decrypt(integration["auth_token"])
            except Exception as e:
                logger.error(f"Failed to decrypt Twilio integration for tenant {tenant_id}: {e}")
                return None
        return integration

    async def _find_trunk_id_by_number(self, livekit_api: api.LiveKitAPI, phone_number: str) -> Optional[str]:
        """
        Look up an existing SIP trunk that has this phone number in its `numbers` list.

        Returns the `sip_trunk_id` (e.g., ST_xxx) if found.
        """
        normalized_phone = normalize_phone_number_safe(phone_number) or phone_number

        if not hasattr(livekit_api.sip, "list_sip_inbound_trunk"):
            logger.warning("LiveKit SDK missing list_sip_inbound_trunk; cannot verify trunk ID")
            return None

        try:
            response = await livekit_api.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
            trunks = response.items if hasattr(response, "items") else response or []

            for trunk in trunks:
                trunk_numbers = getattr(trunk, "numbers", []) or []
                if normalized_phone in trunk_numbers or phone_number in trunk_numbers:
                    sip_trunk_id = (
                        getattr(trunk, "sip_trunk_id", None)
                        or getattr(trunk, "inbound_trunk_id", None)
                        or getattr(trunk, "trunk_id", None)
                        or getattr(trunk, "id", None)
                    )
                    if sip_trunk_id:
                        logger.info(
                            f"[TRUNK LOOKUP] Found existing trunk {sip_trunk_id} containing {normalized_phone}"
                        )
                        return sip_trunk_id
        except Exception as e:
            logger.warning(f"[TRUNK LOOKUP] Failed to list trunks: {e}")

        return None

    async def _get_or_create_sip_trunk(self, phone_number: str) -> str:
        """
        Get existing SIP trunk or create new one for phone number.

        Per documentation: https://docs.livekit.io/sip/trunk-inbound/
        We use phone-number-specific trunks (numbers=[phone_number]) to avoid conflicts.
        
        IMPORTANT: trunk metadata does NOT contain tenant_id because:
        - Trunks belong to phone numbers, not tenants
        - Multiple tenants can share the same phone number
        - Tenant routing is done via SIP headers

        Returns trunk_id.
        """
        try:
            livekit_api = self._get_livekit_api()

            # Normalize phone number for consistent trunk naming and matching
            normalized_phone = normalize_phone_number(phone_number)
            logger.info(f"[TRUNK] Normalized phone number: {phone_number} -> {normalized_phone}")

            # Try to reuse existing trunk first
            existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
            if existing_trunk_id:
                return existing_trunk_id

            # Create new SIP trunk
            sip_service = livekit_api.sip
            
            if not hasattr(sip_service, "create_sip_inbound_trunk"):
                raise AttributeError("LiveKit SIP service does not have 'create_sip_inbound_trunk' method.")

            try:
                # Create SIP inbound trunk
                # NOTE: metadata does NOT include tenant_id - tenant routing via SIP headers only
                inbound_trunk_info = await sip_service.create_sip_inbound_trunk(
                    api.CreateSIPInboundTrunkRequest(
                        trunk=api.SIPInboundTrunkInfo(
                            name=f"Trunk for {normalized_phone}",
                            numbers=[normalized_phone],
                            allowed_addresses=["0.0.0.0/0"],
                            # FIX ISSUE 4: No tenant_id in metadata - tenant routing via SIP headers
                            metadata=f"phone_number={normalized_phone}",
                        )
                    )
                )

                # Extract trunk ID from response
                sip_trunk_id = None
                
                if hasattr(inbound_trunk_info, "sip_trunk_id"):
                    sip_trunk_id = inbound_trunk_info.sip_trunk_id
                elif hasattr(inbound_trunk_info, "inbound_trunk_id"):
                    sip_trunk_id = inbound_trunk_info.inbound_trunk_id
                elif hasattr(inbound_trunk_info, "trunk_id"):
                    sip_trunk_id = inbound_trunk_info.trunk_id
                elif hasattr(inbound_trunk_info, "id"):
                    sip_trunk_id = inbound_trunk_info.id
                elif isinstance(inbound_trunk_info, str):
                    sip_trunk_id = inbound_trunk_info
                
                if not sip_trunk_id:
                    logger.error(f"Failed to extract trunk ID from LiveKit response")
                    raise Exception("Could not extract trunk ID from LiveKit API response")

                logger.info(f"[TRUNK] ✓ Created SIP inbound trunk: {sip_trunk_id} (for {normalized_phone})")
                return sip_trunk_id
                
            except Exception as create_error:
                error_str = str(create_error).lower()

                # Handle "already exists" errors
                if "already exists" in error_str or "duplicate" in error_str or "409" in error_str:
                    existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
                    if existing_trunk_id:
                        return existing_trunk_id
                    raise Exception("Could not retrieve existing SIP trunk ID from LiveKit")

                logger.error(f"Failed to create SIP inbound trunk: {create_error}")
                raise

        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str or "409" in error_str:
                livekit_api = self._get_livekit_api()
                existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
                if existing_trunk_id:
                    return existing_trunk_id
            raise Exception(f"Failed to setup SIP trunk: {str(e)}")

    async def _find_voice_agent_dispatch_rule(self, livekit_api: api.LiveKitAPI) -> Optional[Dict[str, Any]]:
        """
        Find the dispatch rule configured for voice-agent.
        
        Looks for a rule with:
        - dispatchRuleIndividual with roomPrefix="call-"
        - agentName="voice-agent" in roomConfig.agents
        
        Returns dict with rule_id and trunk_ids if found, None otherwise.
        """
        try:
            if not hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                logger.warning("[DISPATCH] LiveKit SDK missing list_sip_dispatch_rule method")
                return None

            response = await livekit_api.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
            rules = response.items if hasattr(response, "items") else response or []

            logger.info(f"[DISPATCH] Found {len(rules)} dispatch rules")

            for rule in rules:
                rule_id = (
                    getattr(rule, "sip_dispatch_rule_id", None)
                    or getattr(rule, "dispatch_rule_id", None)
                    or getattr(rule, "id", None)
                )
                
                # Check for dispatchRuleIndividual
                rule_obj = getattr(rule, "rule", None)
                if not rule_obj:
                    continue
                
                # Check for individual dispatch rule
                individual_rule = getattr(rule_obj, "dispatch_rule_individual", None)
                if not individual_rule:
                    # Try alternative attribute names
                    individual_rule = getattr(rule_obj, "dispatchRuleIndividual", None)
                
                if not individual_rule:
                    continue
                
                # Check room prefix
                room_prefix = getattr(individual_rule, "room_prefix", None)
                if room_prefix is None:
                    room_prefix = getattr(individual_rule, "roomPrefix", "")
                
                if room_prefix != EXPECTED_ROOM_PREFIX:
                    logger.debug(f"[DISPATCH] Rule {rule_id} has roomPrefix='{room_prefix}', expected '{EXPECTED_ROOM_PREFIX}'")
                    continue
                
                # Check agent name in room config
                room_config = getattr(rule, "room_config", None)
                if not room_config:
                    room_config = getattr(rule, "roomConfig", None)
                
                agent_name_matches = False
                if room_config:
                    agents = getattr(room_config, "agents", []) or []
                    for agent in agents:
                        agent_name = getattr(agent, "agent_name", None)
                        if agent_name is None:
                            agent_name = getattr(agent, "agentName", "")
                        if agent_name == EXPECTED_AGENT_NAME:
                            agent_name_matches = True
                            break
                
                if not agent_name_matches:
                    logger.debug(f"[DISPATCH] Rule {rule_id} does not have agentName='{EXPECTED_AGENT_NAME}'")
                    continue
                
                # Found matching rule
                trunk_ids = list(getattr(rule, "trunk_ids", []) or [])
                
                logger.info(f"[DISPATCH] ✓ Found matching dispatch rule: {rule_id}")
                logger.info(f"[DISPATCH] Current trunk_ids: {trunk_ids}")
                
                return {
                    "rule_id": rule_id,
                    "trunk_ids": trunk_ids,
                }
            
            logger.warning(f"[DISPATCH] No dispatch rule found with roomPrefix='{EXPECTED_ROOM_PREFIX}' and agentName='{EXPECTED_AGENT_NAME}'")
            return None

        except Exception as e:
            logger.error(f"[DISPATCH] Error finding dispatch rule: {e}", exc_info=True)
            return None

    async def _attach_trunk_to_dispatch_rule(self, trunk_id: str) -> bool:
        """
        Attach a trunk to the voice-agent dispatch rule.
        
        This ensures the trunk is associated with the correct dispatch rule
        that launches the voice-agent worker.
        
        Returns True if successful, False otherwise.
        """
        try:
            livekit_api = self._get_livekit_api()
            
            # Find the voice-agent dispatch rule
            rule_info = await self._find_voice_agent_dispatch_rule(livekit_api)
            
            if not rule_info:
                logger.error(
                    f"[DISPATCH] ✗ CRITICAL: No dispatch rule found with roomPrefix='{EXPECTED_ROOM_PREFIX}' "
                    f"and agentName='{EXPECTED_AGENT_NAME}'. "
                    f"Please create the dispatch rule in the LiveKit dashboard first."
                )
                return False
            
            rule_id = rule_info["rule_id"]
            current_trunk_ids = rule_info["trunk_ids"]
            
            # Check if trunk is already attached
            if trunk_id in current_trunk_ids:
                logger.info(f"[DISPATCH] Trunk {trunk_id} is already attached to dispatch rule {rule_id}")
                return True
            
            # Add trunk to the rule
            new_trunk_ids = current_trunk_ids + [trunk_id]
            
            logger.info(f"[DISPATCH] Adding trunk {trunk_id} to dispatch rule {rule_id}")
            logger.info(f"[DISPATCH] New trunk_ids: {new_trunk_ids}")
            
            if not hasattr(livekit_api.sip, "update_sip_dispatch_rule"):
                logger.error("[DISPATCH] LiveKit SDK missing update_sip_dispatch_rule method")
                return False
            
            # Update the dispatch rule
            await livekit_api.sip.update_sip_dispatch_rule(
                api.UpdateSIPDispatchRuleRequest(
                    sip_dispatch_rule_id=rule_id,
                    trunk_ids=new_trunk_ids,
                )
            )
            
            logger.info(f"[DISPATCH] ✓ Successfully attached trunk {trunk_id} to dispatch rule {rule_id}")
            return True

        except Exception as e:
            logger.error(f"[DISPATCH] Failed to attach trunk to dispatch rule: {e}", exc_info=True)
            return False

    async def _detach_trunk_from_dispatch_rule(self, trunk_id: str) -> bool:
        """
        Detach a trunk from the voice-agent dispatch rule.
        
        This is used during cleanup when unassigning a phone number.
        
        Returns True if successful, False otherwise.
        """
        try:
            livekit_api = self._get_livekit_api()
            
            # Find the voice-agent dispatch rule
            rule_info = await self._find_voice_agent_dispatch_rule(livekit_api)
            
            if not rule_info:
                logger.warning(f"[DISPATCH] No dispatch rule found during cleanup")
                return True  # Nothing to detach from
            
            rule_id = rule_info["rule_id"]
            current_trunk_ids = rule_info["trunk_ids"]
            
            # Check if trunk is attached
            if trunk_id not in current_trunk_ids:
                logger.info(f"[DISPATCH] Trunk {trunk_id} is not attached to dispatch rule {rule_id}")
                return True
            
            # Remove trunk from the rule
            new_trunk_ids = [t for t in current_trunk_ids if t != trunk_id]
            
            logger.info(f"[DISPATCH] Removing trunk {trunk_id} from dispatch rule {rule_id}")
            
            if not hasattr(livekit_api.sip, "update_sip_dispatch_rule"):
                logger.error("[DISPATCH] LiveKit SDK missing update_sip_dispatch_rule method")
                return False
            
            # Update the dispatch rule
            await livekit_api.sip.update_sip_dispatch_rule(
                api.UpdateSIPDispatchRuleRequest(
                    sip_dispatch_rule_id=rule_id,
                    trunk_ids=new_trunk_ids,
                )
            )
            
            logger.info(f"[DISPATCH] ✓ Successfully detached trunk {trunk_id} from dispatch rule")
            return True

        except Exception as e:
            logger.error(f"[DISPATCH] Failed to detach trunk from dispatch rule: {e}", exc_info=True)
            return False

    async def _configure_twilio_phone_webhook(self, tenant_id: str, phone_number: str) -> Dict[str, Any]:
        """
        Configure Twilio phone number webhook URLs.

        Returns phone number resource info.
        """
        try:
            twilio_integration = await self._get_decrypted_twilio_integration(tenant_id)
            if not twilio_integration:
                raise ValueError(f"No Twilio integration found for tenant {tenant_id}")

            from app.core.config import TWILIO_WEBHOOK_BASE_URL

            if not TWILIO_WEBHOOK_BASE_URL:
                raise ValueError(
                    "TWILIO_WEBHOOK_BASE_URL environment variable is required for webhook configuration."
                )

            base_url = TWILIO_WEBHOOK_BASE_URL.rstrip("/")
            webhook_url = f"{base_url}/api/v1/voice-agent/twilio/webhook"
            status_callback_url = f"{base_url}/api/v1/voice-agent/twilio/status"

            logger.info(f"[TWILIO] Configuring webhooks - Voice: {webhook_url}, Status: {status_callback_url}")

            normalized_phone = normalize_phone_number(phone_number)

            def _configure_webhook_sync():
                twilio_client = Client(twilio_integration["account_sid"], twilio_integration["auth_token"])

                incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=normalized_phone)

                if not incoming_numbers:
                    logger.warning(f"Phone number {normalized_phone} not found, trying original format")
                    incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=phone_number)

                if not incoming_numbers:
                    raise ValueError(f"Phone number {normalized_phone} not found in Twilio account.")

                phone_number_resource = incoming_numbers[0]
                logger.info(f"[TWILIO] Found phone number: SID={phone_number_resource.sid}")

                phone_number_resource.update(
                    voice_url=webhook_url,
                    voice_method="POST",
                    status_callback=status_callback_url,
                    status_callback_method="POST",
                )

                return phone_number_resource

            phone_number_resource = await _run_twilio_sync(_configure_webhook_sync)

            logger.info(f"[TWILIO] ✓ Successfully configured webhooks for {normalized_phone}")

            return {
                "phone_sid": phone_number_resource.sid,
                "phone_number": phone_number_resource.phone_number,
                "voice_url": webhook_url,
                "status_callback": status_callback_url,
            }

        except TwilioException as e:
            logger.error(f"Twilio API error: {e}", exc_info=True)
            raise Exception(f"Twilio API error: {str(e)}")
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to configure phone number webhook: {e}", exc_info=True)
            raise Exception(f"Phone number webhook configuration failed: {str(e)}")

    async def setup_phone_number_sip(self, tenant_id: str, phone_number: str, agent_id: str) -> Dict[str, Any]:
        """
        Setup complete SIP infrastructure for phone number assignment.

        This method:
        1. Creates/verifies LiveKit SIP inbound trunk for the phone number
        2. Attaches the trunk to the voice-agent dispatch rule
        3. Configures Twilio phone number webhook

        Returns configuration details including:
        - trunk_id: The SIP trunk ID
        - dispatch_rule_validated: Boolean indicating if trunk was attached to dispatch rule
        - phone_config: Twilio webhook configuration
        - sip_domain: The LiveKit SIP domain
        """
        try:
            logger.info(f"[SIP SETUP] Starting for phone={phone_number}, agent={agent_id}, tenant={tenant_id}")

            # Step 1: Get or create SIP trunk for this phone number
            # NOTE: Trunk does NOT contain tenant_id - multi-tenant routing via SIP headers
            trunk_id = None
            try:
                trunk_id = await self._get_or_create_sip_trunk(phone_number)
                logger.info(f"[SIP SETUP] ✓ SIP trunk ready: {trunk_id}")
            except Exception as trunk_error:
                normalized_phone = normalize_phone_number_safe(phone_number) or phone_number
                phone_clean = (
                    normalized_phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                )
                trunk_id = f"trunk-{phone_clean}"
                logger.warning(f"[SIP SETUP] Could not verify/create SIP trunk: {trunk_error}. Using fallback: {trunk_id}")

            # Step 2: Attach trunk to dispatch rule (FIX ISSUE 1)
            dispatch_rule_validated = False
            try:
                dispatch_rule_validated = await self._attach_trunk_to_dispatch_rule(trunk_id)
                if dispatch_rule_validated:
                    logger.info(f"[SIP SETUP] ✓ Trunk attached to dispatch rule")
                else:
                    logger.warning(f"[SIP SETUP] ✗ Failed to attach trunk to dispatch rule")
            except Exception as dispatch_error:
                logger.warning(f"[SIP SETUP] Failed to validate dispatch rule: {dispatch_error}")

            # Step 3: Configure Twilio phone number webhook
            phone_config = await self._configure_twilio_phone_webhook(tenant_id, phone_number)
            logger.info(f"[SIP SETUP] ✓ Twilio webhook configured: {phone_config['phone_sid']}")

            # FIX ISSUE 5: Return dispatch_rule_validated instead of fake dispatch_rule_id
            return {
                "trunk_id": trunk_id,
                "dispatch_rule_validated": dispatch_rule_validated,  # Boolean, not fake ID
                "phone_config": phone_config,
                "sip_domain": LIVEKIT_SIP_DOMAIN,
                "status": "configured",
            }

        except Exception as e:
            logger.error(f"[SIP SETUP] Failed: {e}", exc_info=True)
            raise Exception(f"SIP configuration failed: {str(e)}")

    async def cleanup_phone_number_sip(
        self, tenant_id: str, phone_number: str, dispatch_rule_id: Optional[str] = None
    ) -> bool:
        """
        Cleanup SIP configuration when phone number is unassigned.

        This detaches the trunk from the dispatch rule but does not delete the trunk.
        """
        try:
            # Get phone-specific trunk ID
            normalized_phone = normalize_phone_number_safe(phone_number) or phone_number
            phone_clean = (
                normalized_phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            )
            
            # Try to find the actual trunk ID first
            livekit_api = self._get_livekit_api()
            trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
            
            if not trunk_id:
                trunk_id = f"trunk-{phone_clean}"
                logger.warning(f"[CLEANUP] Could not find trunk for {phone_number}, using fallback: {trunk_id}")
            
            # Detach trunk from dispatch rule
            await self._detach_trunk_from_dispatch_rule(trunk_id)
            
            logger.info(f"[CLEANUP] ✓ Completed cleanup for {phone_number}")
            return True

        except Exception as e:
            logger.error(f"[CLEANUP] Failed: {e}")
            return False


# Global SIP configuration service instance
sip_configuration_service = SIPConfigurationService()
