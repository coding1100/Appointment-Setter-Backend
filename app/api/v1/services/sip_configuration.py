"""
SIP Configuration Service for automating LiveKit and Twilio SIP setup.
Handles SIP trunk, dispatch rules, and phone number webhook configuration.

ARCHITECTURE:
- Each phone number gets its own SIP inbound trunk
- Each phone number gets its own dispatch rule (auto-created)
- ALL dispatch rules use single global agentName: "voice-agent"
- One worker handles ALL phone numbers (multi-tenant design)
- Dispatch rule uses Individual mode with roomPrefix="call-"
- Tenant routing is handled via SIP headers (X-LK-TenantId, X-LK-CallId)
- Worker extracts phone number from SIP headers (X-LK-CalledNumber)
"""

import asyncio
import logging
import re
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
# Single global agent name - one worker handles all phone numbers
GLOBAL_AGENT_NAME = "voice-agent"


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

    def _extract_trunk_id_from_conflict_error(self, error_message: str) -> Optional[str]:
        """
        Extract the conflicting trunk ID from a LiveKit conflict error message.
        
        Error format example:
        "Conflicting inbound SIP Trunks: "<new>" and "ST_s5G6WaGoPVL4", using the same number(s)..."
        
        Returns the trunk ID (e.g., "ST_s5G6WaGoPVL4") if found, None otherwise.
        """
        # Pattern to match trunk IDs in the error message
        # Look for patterns like "ST_xxx" or similar trunk ID formats
        patterns = [
            r'"([ST]_[A-Za-z0-9]+)"',  # Matches "ST_xxxxx" format
            r'and\s+"([A-Za-z0-9_]+)"',  # Matches trunk ID after "and"
            r'Trunk[^"]*"([A-Za-z0-9_]+)"',  # Matches trunk ID in various formats
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, error_message)
            for match in matches:
                # Skip "<new>" placeholder
                if match.lower() not in ["<new>", "new"] and match.startswith(("ST_", "IT_", "TR_")):
                    logger.debug(f"[TRUNK] Extracted trunk ID from conflict error: {match}")
                    return match
        
        logger.warning(f"[TRUNK] Could not extract trunk ID from conflict error: {error_message}")
        return None

    async def _verify_trunk_exists(self, livekit_api: api.LiveKitAPI, trunk_id: str) -> bool:
        """
        Verify that a trunk ID exists and is valid in LiveKit.
        
        Returns True if trunk exists, False otherwise.
        """
        if not trunk_id or not trunk_id.startswith(("ST_", "IT_", "TR_")):
            logger.warning(f"[TRUNK] Invalid trunk ID format: {trunk_id}")
            return False
        
        try:
            if not hasattr(livekit_api.sip, "list_sip_inbound_trunk"):
                logger.warning("[TRUNK] Cannot verify trunk - SDK missing list method")
                return False
            
            response = await livekit_api.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
            trunks = response.items if hasattr(response, "items") else response or []
            
            for trunk in trunks:
                trunk_id_attr = (
                    getattr(trunk, "sip_trunk_id", None)
                    or getattr(trunk, "inbound_trunk_id", None)
                    or getattr(trunk, "trunk_id", None)
                    or getattr(trunk, "id", None)
                )
                if trunk_id_attr == trunk_id:
                    logger.info(f"[TRUNK] Verified trunk exists: {trunk_id}")
                    return True
            
            logger.warning(f"[TRUNK] Trunk {trunk_id} not found in LiveKit")
            return False
            
        except Exception as e:
            logger.error(f"[TRUNK] Failed to verify trunk existence: {e}")
            return False

    async def _delete_sip_trunk(self, livekit_api: api.LiveKitAPI, trunk_id: str) -> bool:
        """
        Delete a SIP inbound trunk by ID.
        
        Returns True if successful, False otherwise.
        """
        if not trunk_id or not trunk_id.startswith(("ST_", "IT_", "TR_")):
            logger.warning(f"[TRUNK] Invalid trunk ID format for deletion: {trunk_id}")
            return False
        
        try:
            sip_service = livekit_api.sip
            
            if not hasattr(sip_service, "delete_sip_inbound_trunk"):
                logger.warning("[TRUNK] SDK missing delete_sip_inbound_trunk method")
                return False
            
            # Try different request formats
            try:
                # Try with sip_trunk_id parameter
                await sip_service.delete_sip_inbound_trunk(
                    api.DeleteSIPInboundTrunkRequest(sip_trunk_id=trunk_id)
                )
                logger.info(f"[TRUNK] ✓ Deleted trunk {trunk_id}")
                return True
            except (TypeError, AttributeError):
                # Try alternative format
                try:
                    await sip_service.delete_sip_inbound_trunk(
                        api.DeleteSIPInboundTrunkRequest(inbound_trunk_id=trunk_id)
                    )
                    logger.info(f"[TRUNK] ✓ Deleted trunk {trunk_id}")
                    return True
                except (TypeError, AttributeError):
                    # Try with trunk_id parameter
                    try:
                        await sip_service.delete_sip_inbound_trunk(
                            api.DeleteSIPInboundTrunkRequest(trunk_id=trunk_id)
                        )
                        logger.info(f"[TRUNK] ✓ Deleted trunk {trunk_id}")
                        return True
                    except Exception as e:
                        logger.error(f"[TRUNK] Failed to delete trunk {trunk_id}: {e}")
                        return False
                        
        except Exception as e:
            logger.error(f"[TRUNK] Failed to delete trunk {trunk_id}: {e}")
            return False

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

            # CRITICAL: One trunk per phone number - delete any existing trunk first
            # This ensures no conflicts and clean state for each phone number
            existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
            if existing_trunk_id:
                logger.info(f"[TRUNK] Found existing trunk {existing_trunk_id} for {normalized_phone}, deleting to create fresh trunk...")
                await self._delete_sip_trunk(livekit_api, existing_trunk_id)
                logger.info(f"[TRUNK] ✓ Deleted existing trunk {existing_trunk_id}")

            # Create new SIP trunk (always create fresh, never reuse)
            sip_service = livekit_api.sip
            
            if not hasattr(sip_service, "create_sip_inbound_trunk"):
                raise AttributeError("LiveKit SIP service does not have 'create_sip_inbound_trunk' method.")

            try:
                # Create SIP inbound trunk with custom header mapping
                # CRITICAL: Configure headers_to_attributes to map custom SIP headers
                # to LiveKit participant attributes so the worker can read them
                inbound_trunk_info = await sip_service.create_sip_inbound_trunk(
                    api.CreateSIPInboundTrunkRequest(
                        trunk=api.SIPInboundTrunkInfo(
                            name=f"Trunk for {normalized_phone}",
                            allowed_addresses=["0.0.0.0/0"],
                            # CRITICAL: Include ALL SIP headers so custom X-* headers are forwarded
                            # Without this, LiveKit will not receive X-LK-CallId, X-LK-TenantId, etc.
                            include_headers="SIP_ALL_HEADERS",
                            # Map custom SIP headers to participant attributes
                            # Twilio sends X-LK-* headers → LiveKit exposes as lk_* attributes
                            headers_to_attributes={
                                "X-LK-CalledNumber": "lk_callednumber",
                                "X-LK-TenantId": "lk_tenantid",
                                "X-LK-CallId": "lk_callid",
                            },
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
                error_str = str(create_error)
                error_str_lower = error_str.lower()

                # Handle "conflicting" trunk errors - delete the conflicting trunk and retry
                if "conflicting" in error_str_lower or "conflict" in error_str_lower:
                    conflicting_trunk_id = self._extract_trunk_id_from_conflict_error(error_str)
                    if conflicting_trunk_id:
                        logger.warning(f"[TRUNK] Conflict detected with trunk {conflicting_trunk_id}, deleting it...")
                        try:
                            await self._delete_sip_trunk(livekit_api, conflicting_trunk_id)
                            logger.info(f"[TRUNK] ✓ Deleted conflicting trunk {conflicting_trunk_id}, retrying creation...")
                            # Retry creating the trunk after deleting the conflicting one
                            return await self._get_or_create_sip_trunk(phone_number)
                        except Exception as delete_error:
                            logger.error(f"[TRUNK] Failed to delete conflicting trunk: {delete_error}")
                            raise Exception(f"Trunk conflict detected and could not delete conflicting trunk: {error_str}")
                    else:
                        raise Exception(f"Trunk conflict detected but could not extract trunk ID: {error_str}")

                # Handle "already exists" or "duplicate" errors - delete and retry
                if "already exists" in error_str_lower or "duplicate" in error_str_lower or "409" in error_str:
                    existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
                    if existing_trunk_id:
                        logger.warning(f"[TRUNK] Trunk already exists: {existing_trunk_id}, deleting and recreating...")
                        try:
                            await self._delete_sip_trunk(livekit_api, existing_trunk_id)
                            logger.info(f"[TRUNK] ✓ Deleted existing trunk {existing_trunk_id}, retrying creation...")
                            # Retry creating the trunk after deleting the existing one
                            return await self._get_or_create_sip_trunk(phone_number)
                        except Exception as delete_error:
                            logger.error(f"[TRUNK] Failed to delete existing trunk: {delete_error}")
                            raise Exception(f"Trunk already exists and could not delete it: {error_str}")

                logger.error(f"Failed to create SIP inbound trunk: {create_error}")
                raise

        except Exception as e:
            # All error handling is done in the inner try/except block
            # If we reach here, it's a fatal error that couldn't be recovered
            raise Exception(f"Failed to setup SIP trunk: {str(e)}")

    async def _attach_trunk_to_dispatch_rule(
        self, livekit_api: api.LiveKitAPI, trunk_id: str, phone_number: str
    ) -> Optional[str]:
        """
        Ensure a dispatch rule exists for this phone number.
        
        If none exists, automatically create one.
        If one exists, update it with trunk assignment + agentName.
        
        Returns the dispatch_rule_id if successful, None otherwise.
        """
        try:
            # Use single global agent name for all phone numbers
            agent_name = GLOBAL_AGENT_NAME
            normalized_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            rule_name = f"dispatch-rule-{normalized_phone}"
            
            logger.info(f"[DISPATCH] Ensuring dispatch rule for phone={phone_number}, agent={agent_name}, trunk={trunk_id}")
            
            # 1️⃣ Fetch all dispatch rules
            if not hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                logger.error("[DISPATCH] LiveKit SDK missing list_sip_dispatch_rule method")
                return None
            
            response = await livekit_api.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
            rules = response.items if hasattr(response, "items") else response or []
            
            logger.info(f"[DISPATCH] Found {len(rules)} existing dispatch rules")
            
            # 2️⃣ Find rule by name
            target_rule = None
            for rule in rules:
                rule_name_attr = getattr(rule, "name", None)
                if rule_name_attr == rule_name:
                    target_rule = rule
                    break
            
            # 3️⃣ Create rule if not found
            if target_rule is None:
                logger.info(f"[DISPATCH] Creating new dispatch rule for {phone_number}...")
                
                if not hasattr(livekit_api.sip, "create_sip_dispatch_rule"):
                    logger.error("[DISPATCH] LiveKit SDK missing create_sip_dispatch_rule method")
                    return None
                
                # Build dispatch rule request
                # LiveKit SDK uses snake_case and specific class names
                create_success = False
                rule_id = None
                last_error = None
                
                # Attempt 1: Using standard LiveKit Python SDK (snake_case)
                try:
                    # Build individual dispatch rule
                    individual_rule = api.SIPDispatchRuleIndividual(room_prefix=EXPECTED_ROOM_PREFIX)
                    rule_obj = api.SIPDispatchRule(dispatch_rule_individual=individual_rule)
                    
                    # Try to build room config with agent
                    room_config_obj = None
                    if hasattr(api, "RoomAgentDispatch"):
                        try:
                            agents_list = [api.RoomAgentDispatch(agent_name=agent_name)]
                            room_config_obj = api.RoomConfiguration(agents=agents_list)
                        except Exception as rc_error:
                            logger.debug(f"[DISPATCH] RoomConfiguration with RoomAgentDispatch failed: {rc_error}")
                    
                    # Create request - try with room_config first
                    if room_config_obj:
                        create_req = api.CreateSIPDispatchRuleRequest(
                            name=rule_name,
                            rule=rule_obj,
                            room_config=room_config_obj,
                            trunk_ids=[trunk_id]
                        )
                    else:
                        # Create without room_config
                        create_req = api.CreateSIPDispatchRuleRequest(
                            name=rule_name,
                            rule=rule_obj,
                            trunk_ids=[trunk_id]
                        )
                    
                    logger.debug(f"[DISPATCH] Creating dispatch rule with snake_case API")
                    created = await livekit_api.sip.create_sip_dispatch_rule(create_req)
                    rule_id = (
                        getattr(created, "sip_dispatch_rule_id", None)
                        or getattr(created, "dispatch_rule_id", None)
                        or getattr(created, "id", None)
                    )
                    create_success = True
                    
                    if not room_config_obj:
                        logger.warning(
                            f"[DISPATCH] Created rule {rule_id} without agent config. "
                            f"Agent '{agent_name}' should be added via LiveKit dashboard."
                        )
                    
                except (TypeError, AttributeError, ValueError) as e:
                    last_error = e
                    logger.debug(f"[DISPATCH] Standard API approach failed: {e}, trying minimal creation...")
                    
                    # Attempt 2: Minimal creation without room_config
                    try:
                        individual_rule = api.SIPDispatchRuleIndividual(room_prefix=EXPECTED_ROOM_PREFIX)
                        rule_obj = api.SIPDispatchRule(dispatch_rule_individual=individual_rule)
                        
                        create_req = api.CreateSIPDispatchRuleRequest(
                            name=rule_name,
                            rule=rule_obj,
                            trunk_ids=[trunk_id]
                        )
                        
                        logger.debug(f"[DISPATCH] Creating minimal dispatch rule")
                        created = await livekit_api.sip.create_sip_dispatch_rule(create_req)
                        rule_id = (
                            getattr(created, "sip_dispatch_rule_id", None)
                            or getattr(created, "dispatch_rule_id", None)
                            or getattr(created, "id", None)
                        )
                        create_success = True
                        
                        logger.warning(
                            f"[DISPATCH] Created rule {rule_id} without agent config. "
                            f"Agent '{agent_name}' must be added via LiveKit dashboard."
                        )
                        
                    except Exception as fallback_error:
                        last_error = fallback_error
                        logger.error(f"[DISPATCH] Fallback creation also failed: {fallback_error}", exc_info=True)
                
                if create_success and rule_id:
                    logger.info(f"[DISPATCH] ✓ Created dispatch rule {rule_id} for phone={phone_number}")
                    logger.info(f"[DISPATCH] Rule ready: phone={phone_number}, agent={agent_name}, trunk={trunk_id}")
                    return rule_id
                else:
                    logger.error(f"[DISPATCH] Failed to create dispatch rule: {last_error}")
                    return None
            
            # 4️⃣ Rule already exists - verify trunk is attached
            rule_id = (
                getattr(target_rule, "sip_dispatch_rule_id", None)
                or getattr(target_rule, "dispatch_rule_id", None)
                or getattr(target_rule, "id", None)
            )
            
            if not rule_id:
                logger.error(f"[DISPATCH] Found rule but could not extract rule_id")
                return None
            
            # Check if trunk is already attached
            current_trunk_ids = list(getattr(target_rule, "trunk_ids", []) or [])
            
            if trunk_id in current_trunk_ids:
                logger.info(f"[DISPATCH] ✓ Trunk {trunk_id} already attached to rule {rule_id}")
                logger.info(f"[DISPATCH] Rule ready: phone={phone_number}, agent={agent_name}, trunk={trunk_id}")
                return rule_id
            
            # Trunk not attached - LiveKit API doesn't support updating trunk_ids via UpdateSIPDispatchRuleRequest
            # The only option is to delete and recreate the rule, or accept that trunk isn't bound
            # For now, log warning and return the rule_id - the rule exists and may still work
            logger.warning(
                f"[DISPATCH] Rule {rule_id} exists but trunk {trunk_id} is not attached. "
                f"Current trunks: {current_trunk_ids}. "
                f"LiveKit API doesn't support adding trunks to existing rules. "
                f"Consider deleting and recreating the rule if calls don't work."
            )
            
            # Return rule_id - the rule exists, calls may still route correctly
            # If issues occur, user should unassign/reassign the phone number
            logger.info(f"[DISPATCH] Using existing rule {rule_id} for phone={phone_number}")
            return rule_id

        except Exception as e:
            logger.error(f"[DISPATCH] Failed to attach trunk to dispatch rule: {e}", exc_info=True)
            return None

    async def _delete_dispatch_rule_for_phone(self, phone_number: str) -> bool:
        """
        Delete the dispatch rule for a phone number during cleanup.
        
        Since we have one dispatch rule per phone number, when unassigning
        we delete the entire rule rather than trying to update trunk_ids
        (which the LiveKit API doesn't support).
        
        Returns True if successful or rule doesn't exist, False on error.
        """
        try:
            livekit_api = self._get_livekit_api()
            normalized_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            rule_name = f"dispatch-rule-{normalized_phone}"
            
            # Find the rule by name
            if not hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                logger.warning(f"[CLEANUP] Cannot list dispatch rules")
                return True
            
            response = await livekit_api.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
            rules = response.items if hasattr(response, "items") else response or []
            
            target_rule = None
            for rule in rules:
                rule_name_attr = getattr(rule, "name", None)
                if rule_name_attr == rule_name:
                    target_rule = rule
                    break
            
            if not target_rule:
                logger.info(f"[CLEANUP] No dispatch rule found for {phone_number} during cleanup")
                return True  # Nothing to delete
            
            rule_id = (
                getattr(target_rule, "sip_dispatch_rule_id", None)
                or getattr(target_rule, "dispatch_rule_id", None)
                or getattr(target_rule, "id", None)
            )
            
            if not rule_id:
                logger.warning(f"[CLEANUP] Found rule but could not extract rule_id")
                return True
            
            # Delete the dispatch rule
            logger.info(f"[CLEANUP] Deleting dispatch rule {rule_id} for {phone_number}")
            
            if hasattr(livekit_api.sip, "delete_sip_dispatch_rule"):
                try:
                    await livekit_api.sip.delete_sip_dispatch_rule(
                        api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
                    )
                    logger.info(f"[CLEANUP] ✓ Deleted dispatch rule {rule_id}")
                except Exception as delete_error:
                    logger.warning(f"[CLEANUP] Could not delete dispatch rule: {delete_error}")
                    # Non-critical - continue cleanup
            else:
                logger.warning(f"[CLEANUP] delete_sip_dispatch_rule not available, rule {rule_id} remains")
            
            return True

        except Exception as e:
            logger.error(f"[CLEANUP] Failed to delete dispatch rule: {e}", exc_info=True)
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
            # CRITICAL: Must have a valid trunk ID - no fallback to string IDs
            trunk_id = await self._get_or_create_sip_trunk(phone_number)
            logger.info(f"[SIP SETUP] ✓ SIP trunk ready: {trunk_id}")

            # Step 2: Attach trunk to dispatch rule (auto-create if needed)
            normalized_phone = normalize_phone_number_safe(phone_number) or phone_number
            dispatch_rule_id = None
            try:
                livekit_api = self._get_livekit_api()
                dispatch_rule_id = await self._attach_trunk_to_dispatch_rule(
                    livekit_api, trunk_id=trunk_id, phone_number=normalized_phone
                )
                if dispatch_rule_id:
                    logger.info(f"[SIP SETUP] ✓ Trunk attached to dispatch rule {dispatch_rule_id}")
                else:
                    logger.warning(f"[SIP SETUP] ✗ Failed to attach trunk to dispatch rule")
            except Exception as dispatch_error:
                logger.warning(f"[SIP SETUP] Failed to setup dispatch rule: {dispatch_error}")

            # Step 3: Configure Twilio phone number webhook
            phone_config = await self._configure_twilio_phone_webhook(tenant_id, phone_number)
            logger.info(f"[SIP SETUP] ✓ Twilio webhook configured: {phone_config['phone_sid']}")

            # Return dispatch_rule_id (real ID, not boolean)
            return {
                "trunk_id": trunk_id,
                "dispatch_rule_id": dispatch_rule_id,  # Real dispatch rule ID
                "phone_config": phone_config,
                "sip_domain": LIVEKIT_SIP_DOMAIN,
                "status": "configured",
            }

        except Exception as e:
            logger.error(f"[SIP SETUP] Failed: {e}", exc_info=True)
            raise Exception(f"SIP configuration failed: {str(e)}")

    async def cleanup_phone_number_sip(
        self, tenant_id: str, phone_number: str, dispatch_rule_id: Optional[str] = None, trunk_id: Optional[str] = None
    ) -> bool:
        """
        Cleanup SIP configuration when phone number is unassigned.

        This deletes both the dispatch rule AND the SIP trunk to ensure clean state.
        One trunk per phone number means we must delete it when unassigning.
        """
        try:
            livekit_api = self._get_livekit_api()
            
            # Step 1: Delete dispatch rule for this phone number
            await self._delete_dispatch_rule_for_phone(phone_number)
            logger.info(f"[CLEANUP] ✓ Deleted dispatch rule for {phone_number}")
            
            # Step 2: Delete the SIP trunk (one trunk per phone number)
            # Try to find trunk if trunk_id not provided
            if not trunk_id:
                trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
            
            if trunk_id:
                try:
                    await self._delete_sip_trunk(livekit_api, trunk_id)
                    logger.info(f"[CLEANUP] ✓ Deleted SIP trunk {trunk_id} for {phone_number}")
                except Exception as trunk_delete_error:
                    logger.warning(f"[CLEANUP] Failed to delete trunk {trunk_id}: {trunk_delete_error}")
                    # Non-critical, continue
            else:
                logger.warning(f"[CLEANUP] No trunk ID found for {phone_number}, skipping trunk deletion")
            
            logger.info(f"[CLEANUP] ✓ Completed cleanup for {phone_number}")
            return True

        except Exception as e:
            logger.error(f"[CLEANUP] Failed: {e}")
            return False


# Global SIP configuration service instance
sip_configuration_service = SIPConfigurationService()
