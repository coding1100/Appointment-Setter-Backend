"""
SIP Configuration Service for automating LiveKit and Twilio SIP setup.
Handles SIP trunk, dispatch rules, and phone number webhook configuration.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

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
        
        # Reuse existing instance to avoid unclosed aiohttp sessions
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

    async def _get_or_create_sip_trunk(self, tenant_id: str, phone_number: str) -> str:
        """
        Get existing SIP trunk or create new one for phone number.

        Per documentation: https://docs.livekit.io/sip/trunk-inbound/
        We use phone-number-specific trunks (numbers=[phone_number]) to avoid conflicts.

        Returns trunk_id.
        """
        try:
            livekit_api = self._get_livekit_api()

            # Normalize phone number for consistent trunk naming and matching
            normalized_phone = normalize_phone_number(phone_number)
            logger.info(f"Normalized phone number for SIP trunk: {phone_number} -> {normalized_phone}")

            # Use phone-number-specific trunk name to avoid conflicts
            phone_clean = normalized_phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            trunk_name = f"trunk-{phone_clean}"

            # Get tenant info for naming
            tenant = await tenant_service.get_tenant(tenant_id)
            tenant_name = tenant.get("name", tenant_id) if tenant else tenant_id

            # Try to reuse existing trunk first
            existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
            if existing_trunk_id:
                return existing_trunk_id

            # Try to create SIP trunk - check what methods are actually available
            sip_service = livekit_api.sip
            available_methods = [
                m for m in dir(sip_service) if not m.startswith("_") and callable(getattr(sip_service, m, None))
            ]

            logger.debug(f"Available SIP service methods: {available_methods}")

            # Use the correct method name: create_sip_inbound_trunk (as shown in available methods)
            # Official Documentation: https://docs.livekit.io/sip/api/#createsipinboundtrunk
            if not hasattr(sip_service, "create_sip_inbound_trunk"):
                raise AttributeError(
                    f"LiveKit SIP service does not have 'create_sip_inbound_trunk' method. "
                    f"Available methods: {available_methods}. "
                    f"Please check your LiveKit SDK version."
                )

            # Create SIP inbound trunk using correct API
            # Official Documentation: https://docs.livekit.io/sip/trunk-inbound/
            # Python example: https://docs.livekit.io/sip/trunk-inbound/#inbound-trunk-example
            # FIX: Use phone-number-specific trunk to avoid conflicts
            # Per documentation: Use numbers=[phone_number] instead of numbers=[] (accept all)
            try:
                # Use CreateSIPInboundTrunkRequest with proper structure
                # Based on official docs: CreateSIPInboundTrunkRequest(trunk=SIPInboundTrunkInfo(...))
                # Field is "numbers" (not "inbound_numbers") - see docs example
                # Use phone-number-specific trunk: numbers=[phone_number] to avoid conflicts
                inbound_trunk_info = await sip_service.create_sip_inbound_trunk(
                    api.CreateSIPInboundTrunkRequest(
                        trunk=api.SIPInboundTrunkInfo(
                            # Trunk name
                            name=f"Trunk for {normalized_phone}",
                            # Phone-number-specific: accept calls to this specific phone number
                            # This avoids conflicts with other trunks
                            numbers=[normalized_phone],  # Use normalized format
                            # Accept from any IP (can be restricted to Twilio IPs)
                            allowed_addresses=["0.0.0.0/0"],
                            # Optional metadata
                            metadata=f"tenant_id={tenant_id},phone_number={normalized_phone}",
                        )
                    )
                )

                # Extract trunk ID from response
                # LiveKit returns: { "sipTrunkId": "ST_xxx", ... }
                # In Python, this becomes: inbound_trunk_info.sip_trunk_id
                sip_trunk_id = None
                
                # Try sip_trunk_id first (correct attribute based on API response)
                if hasattr(inbound_trunk_info, "sip_trunk_id"):
                    sip_trunk_id = inbound_trunk_info.sip_trunk_id
                # Fallback to other possible attribute names
                elif hasattr(inbound_trunk_info, "inbound_trunk_id"):
                    sip_trunk_id = inbound_trunk_info.inbound_trunk_id
                elif hasattr(inbound_trunk_info, "trunk_id"):
                    sip_trunk_id = inbound_trunk_info.trunk_id
                elif hasattr(inbound_trunk_info, "id"):
                    sip_trunk_id = inbound_trunk_info.id
                elif isinstance(inbound_trunk_info, str):
                    sip_trunk_id = inbound_trunk_info
                
                if not sip_trunk_id:
                    # Should not happen, but log error if it does
                    logger.error(f"Failed to extract trunk ID from LiveKit response. Response type: {type(inbound_trunk_info)}")
                    raise Exception("Could not extract trunk ID from LiveKit API response")

                logger.info(f"✓ Created SIP inbound trunk with ID: {sip_trunk_id} (for phone {normalized_phone})")
                return sip_trunk_id
            except Exception as create_error:
                error_str = str(create_error)
                error_str_lower = error_str.lower()

                # Handle "already exists" or "duplicate" errors
                if "already exists" in error_str_lower or "duplicate" in error_str_lower or "409" in error_str_lower:
                    existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
                    if existing_trunk_id:
                        return existing_trunk_id
                    logger.error(
                        "LiveKit reported trunk already exists but lookup failed. "
                        "Refusing to fall back to synthetic ID to avoid 404 errors."
                    )
                    raise Exception("Could not retrieve existing SIP trunk ID from LiveKit")

                # Handle trunk conflict - should not happen with phone-number-specific trunks
                # But if it does, try to find existing trunk for this phone number
                if "conflicting" in error_str_lower and "trunk" in error_str_lower:
                    logger.warning(
                        f"Trunk conflict detected: {error_str}. "
                        f"Attempting to find existing trunk for phone {phone_number}..."
                    )
                    try:
                        # Try to list trunks and find the one for this phone number
                        if hasattr(sip_service, "list_sip_inbound_trunk"):
                            # LiveKit API requires a request object
                            existing_trunks_response = await sip_service.list_sip_inbound_trunk(
                                api.ListSIPInboundTrunkRequest()
                            )
                            # Response may have 'items' attribute or be a list directly
                            if hasattr(existing_trunks_response, "items"):
                                existing_trunks = existing_trunks_response.items
                            elif isinstance(existing_trunks_response, list):
                                existing_trunks = existing_trunks_response
                            else:
                                existing_trunks = []
                            for trunk in existing_trunks:
                                trunk_id_attr = (
                                    getattr(trunk, "inbound_trunk_id", None)
                                    or getattr(trunk, "trunk_id", None)
                                    or getattr(trunk, "id", None)
                                )
                                trunk_numbers = getattr(trunk, "numbers", [])

                                # If this trunk is for the same phone number, use it (try both formats)
                                if normalized_phone in trunk_numbers or phone_number in trunk_numbers:
                                    logger.info(
                                        f"Found existing trunk for phone {normalized_phone}: {trunk_id_attr}. Reusing it."
                                    )
                                    return trunk_id_attr or trunk_name

                        # If we can't find it, log and use the trunk_name as fallback
                        logger.warning(
                            f"Could not find existing trunk for phone {normalized_phone}. "
                            f"Using trunk name as fallback: {trunk_name}"
                        )
                        return trunk_name
                    except Exception as list_error:
                        logger.warning(
                            f"Could not list trunks to find existing one: {list_error}. "
                            f"Using trunk name as fallback: {trunk_name}"
                        )
                        return trunk_name

                # For other errors, raise them
                logger.error(f"Failed to create SIP inbound trunk: {create_error}")
                raise

        except AttributeError as e:
            # Enhanced error message with available methods
            logger.error(f"LiveKit SIP API method not found: {e}")
            raise Exception(f"LiveKit SIP API method not available. Please check SDK version. Error: {str(e)}")
        except Exception as e:
            # If trunk already exists, attempt to reuse the real trunk ID
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str or "409" in error_str:
                existing_trunk_id = await self._find_trunk_id_by_number(livekit_api, phone_number)
                if existing_trunk_id:
                    return existing_trunk_id
                raise Exception("Could not retrieve existing SIP trunk ID from LiveKit")
            else:
                logger.error(f"Failed to get or create SIP trunk for tenant {tenant_id}: {e}")
                raise Exception(f"Failed to setup SIP trunk: {str(e)}")

    async def _create_or_update_dispatch_rule(self, tenant_id: str, phone_number: str, trunk_id: str) -> str:
        """
        Create or update LiveKit Direct dispatch rule that routes calls based on SIP URI room name.

        **IMPORTANT FLOW:**
        1. Twilio webhook creates room: `inbound-{caller}-{call_sid}` and stores config in Redis
        2. Twilio dials LiveKit SIP URI with room name in the "To" address
        3. LiveKit Direct dispatch rule extracts room name from SIP URI and dispatches to `voice-worker`
        4. Worker retrieves agent config from Redis and runs the assigned agent

        Official Documentation: https://docs.livekit.io/sip/api/#createsipdispatchrule

        Returns dispatch_rule_id.
        """
        try:
            livekit_api = self._get_livekit_api()

            # Use a global dispatch rule ID for all phone numbers
            # Since we're using Direct dispatch (room name from SIP URI), one rule handles all phone numbers
            rule_id = "dispatch-rule-direct-webhook"

            # Try to check for existing rule (if API method exists)
            try:
                if hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                    # List dispatch rules for this trunk
                    list_request = api.ListSIPDispatchRuleRequest()
                    rules_response = await livekit_api.sip.list_sip_dispatch_rule(list_request)
                    
                    # Check if our global rule already exists
                    if hasattr(rules_response, "items"):
                        rules = rules_response.items
                    elif isinstance(rules_response, list):
                        rules = rules_response
                    else:
                        rules = []
                    
                    for rule in rules:
                        rule_id_attr = getattr(rule, "sip_dispatch_rule_id", None) or getattr(rule, "dispatch_rule_id", None)
                        if rule_id_attr == rule_id:
                            logger.info(f"Found existing Direct dispatch rule: {rule_id}")
                            
                            # Update the rule to include the new trunk_id if not already present
                            try:
                                existing_trunk_ids = list(getattr(rule, "trunk_ids", []))
                                
                                # Filter out invalid trunk IDs (should start with "ST_")
                                # This cleans up any trunk IDs that were incorrectly stored as "trunk-13524030701"
                                valid_trunk_ids = [tid for tid in existing_trunk_ids if tid.startswith("ST_")]
                                if len(valid_trunk_ids) != len(existing_trunk_ids):
                                    invalid_ids = [tid for tid in existing_trunk_ids if not tid.startswith("ST_")]
                                    logger.warning(f"Removing invalid trunk IDs from dispatch rule: {invalid_ids}")
                                    existing_trunk_ids = valid_trunk_ids
                                
                                # Add new trunk if not already present
                                if trunk_id and trunk_id not in existing_trunk_ids:
                                    logger.info(f"Adding trunk to dispatch rule: {trunk_id}")
                                    existing_trunk_ids.append(trunk_id)
                                    
                                    # Update the dispatch rule with cleaned trunk_ids
                                    update_request = api.UpdateSIPDispatchRuleRequest(
                                        sip_dispatch_rule_id=rule_id_attr,  # Use actual rule ID from response
                                        trunk_ids=existing_trunk_ids,
                                    )
                                    await livekit_api.sip.update_sip_dispatch_rule(update_request)
                                    logger.info(f"✓ Updated dispatch rule with trunk: {trunk_id}")
                                    logger.info(f"  - All trunk IDs in rule: {existing_trunk_ids}")
                                else:
                                    logger.info(f"Trunk {trunk_id} already in dispatch rule")
                            except Exception as update_error:
                                logger.warning(f"Could not update dispatch rule with new trunk: {update_error}")
                            
                            return rule_id_attr
            except (AttributeError, Exception) as e:
                # Method doesn't exist or error - we'll try to create
                logger.debug(f"Could not check for existing dispatch rule (may not be supported): {e}")

            # Create dispatch rule using correct API
            # Official Documentation: https://docs.livekit.io/sip/api/#createsipdispatchrule
            if not hasattr(livekit_api.sip, "create_sip_dispatch_rule"):
                logger.warning(
                    f"Dispatch rule creation not available in LiveKit SDK. "
                    f"Skipping dispatch rule - manual configuration required in LiveKit dashboard."
                )
                return rule_id  # Return the rule_id we would have used

            # Create Direct dispatch rule
            # Official Documentation: https://docs.livekit.io/sip/dispatch-rule/
            # Direct dispatch rule uses the room name from the SIP "To" URI
            # This allows the webhook to control room naming and agent assignment via Redis
            try:
                # Structure per official docs and API examples:
                # CreateSIPDispatchRuleRequest(
                #   rule=SIPDispatchRule(
                #     dispatch_rule_direct=SIPDispatchRuleDirect(room_name="")  # Empty = use SIP URI room name
                #   ),
                #   name="Rule Name",
                #   trunk_ids=[...],
                #   room_config={"agents": [{"agentName": "voice-worker"}]}  # CRITICAL for agent dispatch
                # )
                logger.info(f"Creating Direct dispatch rule for tenant {tenant_id} with trunk {trunk_id}")
                
                dispatch_rule_request = api.CreateSIPDispatchRuleRequest(
                    # Core rule configuration
                    rule=api.SIPDispatchRule(
                        # Use Direct dispatch: room name comes from SIP "To" URI
                        # Empty room_name means: use the room name from the SIP URI
                        dispatch_rule_direct=api.SIPDispatchRuleDirect(
                            room_name="",  # Empty = extract room name from SIP URI
                        ),
                    ),
                    # Rule metadata
                    name="Voice Agent Dispatch Rule (Webhook-Managed)",
                    # Associate with trunk(s)
                    trunk_ids=[trunk_id] if trunk_id else [],
                    # Room configuration: CRITICAL - tells LiveKit to wait for agent before answering
                    # This ensures LiveKit sends 200 OK only after worker joins the room
                    # Using dict format as LiveKit SDK may expect this structure
                    room_config=api.RoomConfiguration(
                        agents=[{"agentName": "voice-worker"}]
                    ),
                    # Optional: metadata for tracking
                    metadata=f"tenant_id={tenant_id}",
                )

                dispatch_rule = await livekit_api.sip.create_sip_dispatch_rule(dispatch_rule_request)

                # Handle different response structures
                if hasattr(dispatch_rule, "sip_dispatch_rule_id"):
                    rule_id_result = dispatch_rule.sip_dispatch_rule_id
                elif hasattr(dispatch_rule, "dispatch_rule_id"):
                    rule_id_result = dispatch_rule.dispatch_rule_id
                elif hasattr(dispatch_rule, "rule_id"):
                    rule_id_result = dispatch_rule.rule_id
                elif isinstance(dispatch_rule, str):
                    rule_id_result = dispatch_rule
                else:
                    rule_id_result = rule_id  # Fallback

                logger.info(f"✓ Created Direct dispatch rule: {rule_id_result}")
                logger.info(f"  - Room naming: Uses SIP URI (webhook-controlled)")
                logger.info(f"  - Agent dispatch: voice-worker")
                logger.info(f"  - Trunk: {trunk_id}")
                return rule_id_result
                
            except Exception as create_error:
                # If rule already exists or conflicts, that's fine
                error_str = str(create_error).lower()
                if (
                    "already exists" in error_str
                    or "duplicate" in error_str
                    or "conflicting" in error_str
                    or "409" in error_str
                ):
                    logger.info(
                        f"Direct dispatch rule already exists: {rule_id}. "
                        f"This is expected - one Direct rule handles all phone numbers."
                    )
                    return rule_id
                else:
                    # For other errors, log and re-raise (dispatch rule is critical for automation)
                    logger.error(
                        f"Failed to create Direct dispatch rule: {create_error}. "
                        f"This may require manual configuration in LiveKit dashboard."
                    )
                    raise Exception(f"Dispatch rule creation failed: {str(create_error)}")

        except Exception as e:
            logger.error(f"Failed to create/update dispatch rule: {e}")
            # Dispatch rule is important for automation, so we raise the error
            # This will trigger the rollback in the phone assignment endpoint
            raise Exception(f"Dispatch rule configuration failed: {str(e)}")

    async def _configure_twilio_phone_webhook(self, tenant_id: str, phone_number: str) -> Dict[str, Any]:
        """
        Configure Twilio phone number webhook URLs.

        Official Documentation: https://www.twilio.com/docs/phone-numbers/api/incomingphonenumber-resource#update-an-incomingphonenumber-resource

        This method ALWAYS updates the webhook configuration to ensure it's correct.
        Per Twilio docs, the update() method updates the phone number resource.

        Returns phone number resource info.
        """
        try:
            # Get Twilio integration with decrypted auth_token
            twilio_integration = await self._get_decrypted_twilio_integration(tenant_id)
            if not twilio_integration:
                raise ValueError(f"No Twilio integration found for tenant {tenant_id}")

            # Build webhook URLs - use TWILIO_WEBHOOK_BASE_URL from config
            # Required: TWILIO_WEBHOOK_BASE_URL must be set in environment variables
            # Expected paths: /api/v1/voice-agent/twilio/webhook and /api/v1/voice-agent/twilio/status
            from app.core.config import TWILIO_WEBHOOK_BASE_URL

            if not TWILIO_WEBHOOK_BASE_URL:
                raise ValueError(
                    "TWILIO_WEBHOOK_BASE_URL environment variable is required for webhook configuration. "
                    "Please set it to your public API base URL (e.g., https://your-domain.com)"
                )

            base_url = TWILIO_WEBHOOK_BASE_URL.rstrip("/")
            webhook_url = f"{base_url}/api/v1/voice-agent/twilio/webhook"
            status_callback_url = f"{base_url}/api/v1/voice-agent/twilio/status"

            logger.info(f"Configuring webhooks - Voice: {webhook_url}, Status: {status_callback_url}")

            # Normalize phone number for Twilio API lookup (Twilio expects E.164 format)
            normalized_phone = normalize_phone_number(phone_number)
            logger.info(f"Normalized phone number for Twilio lookup: {phone_number} -> {normalized_phone}")

            def _configure_webhook_sync():
                # Create Twilio client
                twilio_client = Client(twilio_integration["account_sid"], twilio_integration["auth_token"])

                # Find the phone number resource in Twilio
                # Twilio API expects phone number in E.164 format
                incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=normalized_phone)

                if not incoming_numbers:
                    # Try without normalization in case Twilio has it in different format
                    logger.warning(f"Phone number {normalized_phone} not found, trying original format: {phone_number}")
                    incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=phone_number)

                if not incoming_numbers:
                    raise ValueError(
                        f"Phone number {normalized_phone} not found in Twilio account. "
                        f"Please ensure the phone number exists in your Twilio account."
                    )

                phone_number_resource = incoming_numbers[0]
                logger.info(
                    f"Found Twilio phone number: SID={phone_number_resource.sid}, "
                    f"Number={phone_number_resource.phone_number}"
                )

                # ALWAYS update webhook configuration to ensure it's correct
                # Per Twilio documentation: https://www.twilio.com/docs/phone-numbers/api/incomingphonenumber-resource#update-an-incomingphonenumber-resource
                phone_number_resource.update(
                    voice_url=webhook_url,
                    voice_method="POST",
                    status_callback=status_callback_url,
                    status_callback_method="POST",
                )

                return phone_number_resource

            # Run Twilio operations in thread pool
            phone_number_resource = await _run_twilio_sync(_configure_webhook_sync)

            logger.info(f"✓ Successfully updated webhook configuration for phone number {normalized_phone}")

            # Note: Twilio's update() method is synchronous and should take effect immediately
            # We log the returned values to verify they were set correctly
            logger.info(
                f"Webhook configuration result: voice_url={phone_number_resource.voice_url}, "
                f"status_callback={phone_number_resource.status_callback}"
            )

            return {
                "phone_sid": phone_number_resource.sid,
                "phone_number": phone_number_resource.phone_number,
                "voice_url": webhook_url,
                "status_callback": status_callback_url,
            }

        except TwilioException as e:
            logger.error(f"Twilio API error configuring phone number {phone_number}: {e}", exc_info=True)
            raise Exception(f"Twilio API error: {str(e)}")
        except ValueError as e:
            logger.error(f"Validation error configuring phone number webhook: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to configure phone number webhook: {e}", exc_info=True)
            raise Exception(f"Phone number webhook configuration failed: {str(e)}")

    async def setup_phone_number_sip(self, tenant_id: str, phone_number: str, agent_id: str) -> Dict[str, Any]:
        """
        Setup complete SIP infrastructure for phone number assignment.

        This method:
        1. Verifies/creates LiveKit SIP trunk
        2. Creates/updates dispatch rule for phone number
        3. Configures Twilio phone number webhook

        Official Documentation:
        - LiveKit: https://docs.livekit.io/sip/api/
        - Twilio: https://www.twilio.com/docs/voice/sip/api

        Returns configuration details.
        """
        try:
            logger.info(f"Setting up SIP configuration for phone {phone_number}, agent {agent_id}, tenant {tenant_id}")

            # Step 1: Get or create SIP trunk for this specific phone number
            # FIX: Changed from tenant-level to phone-number-specific trunk
            trunk_id = None
            try:
                trunk_id = await self._get_or_create_sip_trunk(tenant_id, phone_number)
                logger.info(f"✓ SIP trunk ready: {trunk_id}")
            except Exception as trunk_error:
                # Trunk might already exist
                # Use phone-number-based trunk name as fallback
                normalized_phone = normalize_phone_number_safe(phone_number) or phone_number
                phone_clean = (
                    normalized_phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                )
                trunk_id = f"trunk-{phone_clean}"
                logger.warning(
                    f"Could not verify/create SIP trunk (may already exist): {trunk_error}. "
                    f"Using trunk name: {trunk_id}. Continuing with webhook configuration..."
                )

            # Step 2: Create or update dispatch rule (optional but recommended)
            dispatch_rule_id = None
            try:
                dispatch_rule_id = await self._create_or_update_dispatch_rule(tenant_id, phone_number, trunk_id)
                logger.info(f"✓ Dispatch rule ready: {dispatch_rule_id}")
            except Exception as dispatch_error:
                # Dispatch rules are helpful but not strictly required if using TwiML direct routing
                logger.warning(f"Failed to create dispatch rule (non-critical): {dispatch_error}")
                logger.info("Continuing with webhook configuration - TwiML routing will still work")

            # Step 3: Configure Twilio phone number webhook
            phone_config = await self._configure_twilio_phone_webhook(tenant_id, phone_number)
            logger.info(f"✓ Twilio webhook configured: {phone_config['phone_sid']}")

            # Return configuration summary
            # Use phone-number-based trunk ID as fallback if trunk_id not set
            if not trunk_id:
                normalized_phone = normalize_phone_number_safe(phone_number) or phone_number
                phone_clean = (
                    normalized_phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                )
                trunk_id = f"trunk-{phone_clean}"

            return {
                "trunk_id": trunk_id,
                "dispatch_rule_id": dispatch_rule_id,
                "phone_config": phone_config,
                "sip_domain": LIVEKIT_SIP_DOMAIN,
                "status": "configured",
            }

        except Exception as e:
            logger.error(f"Failed to setup SIP configuration: {e}", exc_info=True)
            raise Exception(f"SIP configuration failed: {str(e)}")

    async def cleanup_phone_number_sip(
        self, tenant_id: str, phone_number: str, dispatch_rule_id: Optional[str] = None
    ) -> bool:
        """
        Cleanup SIP configuration when phone number is unassigned.

        **NOTE:** The Direct dispatch rule is shared across all phone numbers,
        so we only remove the phone-specific trunk from the rule, not the rule itself.
        """
        try:
            livekit_api = self._get_livekit_api()
            
            # Get phone-specific trunk ID
            phone_clean = (
                phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            )
            trunk_id = f"trunk-{phone_clean}"
            
            # Since we use a shared Direct dispatch rule, we should remove this trunk from the rule
            # rather than deleting the rule itself (which would affect all other phone numbers)
            if dispatch_rule_id:
                try:
                    # Get current dispatch rule
                    if hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                        list_request = api.ListSIPDispatchRuleRequest()
                        rules_response = await livekit_api.sip.list_sip_dispatch_rule(list_request)
                        
                        if hasattr(rules_response, "items"):
                            rules = rules_response.items
                        elif isinstance(rules_response, list):
                            rules = rules_response
                        else:
                            rules = []
                        
                        for rule in rules:
                            rule_id_attr = getattr(rule, "sip_dispatch_rule_id", None) or getattr(rule, "dispatch_rule_id", None)
                            if rule_id_attr == dispatch_rule_id:
                                # Remove this trunk from the rule
                                existing_trunk_ids = list(getattr(rule, "trunk_ids", []))
                                if trunk_id in existing_trunk_ids:
                                    existing_trunk_ids.remove(trunk_id)
                                    logger.info(f"Removing trunk {trunk_id} from dispatch rule {dispatch_rule_id}")
                                    
                                    # Update the dispatch rule
                                    if hasattr(livekit_api.sip, "update_sip_dispatch_rule"):
                                        update_request = api.UpdateSIPDispatchRuleRequest(
                                            sip_dispatch_rule_id=dispatch_rule_id,
                                            trunk_ids=existing_trunk_ids,
                                        )
                                        await livekit_api.sip.update_sip_dispatch_rule(update_request)
                                        logger.info(f"✓ Removed trunk {trunk_id} from dispatch rule")
                                else:
                                    logger.info(f"Trunk {trunk_id} not found in dispatch rule")
                                break
                except Exception as e:
                    logger.warning(f"Failed to update dispatch rule during cleanup: {e}")
                    # Non-critical, continue
            
            # Optionally delete the trunk (commented out for now to avoid accidental deletions)
            # Uncomment if you want to fully remove trunks when unassigning phone numbers
            # try:
            #     if hasattr(livekit_api.sip, "delete_sip_inbound_trunk"):
            #         await livekit_api.sip.delete_sip_inbound_trunk(
            #             api.DeleteSIPInboundTrunkRequest(sip_trunk_id=trunk_id)
            #         )
            #         logger.info(f"Deleted SIP trunk {trunk_id} for phone {phone_number}")
            # except Exception as e:
            #     logger.warning(f"Failed to delete SIP trunk: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup SIP configuration: {e}")
            return False


# Global SIP configuration service instance
sip_configuration_service = SIPConfigurationService()
