"""
SIP Configuration Service for automating LiveKit and Twilio SIP setup.
Handles SIP trunk, dispatch rules, and phone number webhook configuration.
"""

import logging
from typing import Any, Dict, Optional

from livekit import api
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.api.v1.services.tenant import tenant_service
from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_SIP_DOMAIN,
    LIVEKIT_URL,
    TWILIO_WEBHOOK_BASE_URL,
)
from app.core.encryption import encryption_service
from app.services.firebase import firebase_service

# Configure logging
logger = logging.getLogger(__name__)


class SIPConfigurationService:
    """Service for managing SIP configuration between LiveKit and Twilio."""

    def __init__(self):
        """Initialize SIP configuration service."""
        pass

    def _get_livekit_api(self) -> api.LiveKitAPI:
        """Get LiveKit API client instance."""
        if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
            raise ValueError(
                "LiveKit configuration is missing. Please set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET."
            )
        return api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)

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

    async def _get_or_create_sip_trunk(self, tenant_id: str, phone_number: str) -> str:
        """
        Get existing SIP trunk or create new one for phone number.

        Per documentation: https://docs.livekit.io/sip/trunk-inbound/
        We use phone-number-specific trunks (numbers=[phone_number]) to avoid conflicts.

        Returns trunk_id.
        """
        try:
            livekit_api = self._get_livekit_api()
            # Use phone-number-specific trunk name to avoid conflicts
            phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            trunk_name = f"trunk-{phone_clean}"

            # Get tenant info for naming
            tenant = await tenant_service.get_tenant(tenant_id)
            tenant_name = tenant.get("name", tenant_id) if tenant else tenant_id

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

            # Check if trunk already exists by listing
            try:
                if hasattr(sip_service, "list_sip_inbound_trunk"):
                    existing_trunks = await sip_service.list_sip_inbound_trunk()
                    for trunk in existing_trunks:
                        trunk_id_attr = (
                            getattr(trunk, "inbound_trunk_id", None)
                            or getattr(trunk, "trunk_id", None)
                            or getattr(trunk, "id", None)
                        )
                        trunk_numbers = getattr(trunk, "numbers", [])

                        # Check if this trunk is for the same phone number
                        if phone_number in trunk_numbers:
                            logger.info(f"Found existing SIP inbound trunk for phone {phone_number}: {trunk_id_attr}")
                            return trunk_id_attr or trunk_name
            except Exception as list_error:
                logger.debug(f"Could not list existing trunks (may not be supported): {list_error}")

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
                            name=f"Trunk for {phone_number}",
                            # Phone-number-specific: accept calls to this specific phone number
                            # This avoids conflicts with other trunks
                            numbers=[phone_number],  # Field is "numbers", NOT "inbound_numbers"
                            # Accept from any IP (can be restricted to Twilio IPs)
                            allowed_addresses=["0.0.0.0/0"],
                            # Optional metadata
                            metadata=f"tenant_id={tenant_id},phone_number={phone_number}",
                        )
                    )
                )

                # Extract trunk ID from response
                if hasattr(inbound_trunk_info, "inbound_trunk_id"):
                    sip_trunk_id = inbound_trunk_info.inbound_trunk_id
                elif hasattr(inbound_trunk_info, "trunk_id"):
                    sip_trunk_id = inbound_trunk_info.trunk_id
                elif hasattr(inbound_trunk_info, "id"):
                    sip_trunk_id = inbound_trunk_info.id
                elif isinstance(inbound_trunk_info, str):
                    sip_trunk_id = inbound_trunk_info
                else:
                    # If we can't extract ID, use a generated one based on tenant
                    sip_trunk_id = trunk_name

                logger.info(f"Created SIP inbound trunk for tenant {tenant_id}: {sip_trunk_id}")
                return sip_trunk_id
            except Exception as create_error:
                error_str = str(create_error)
                error_str_lower = error_str.lower()

                # Handle "already exists" or "duplicate" errors
                if "already exists" in error_str_lower or "duplicate" in error_str_lower or "409" in error_str_lower:
                    logger.info(f"SIP trunk already exists for tenant {tenant_id}, using existing: {trunk_name}")
                    return trunk_name

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
                            existing_trunks = await sip_service.list_sip_inbound_trunk()
                            for trunk in existing_trunks:
                                trunk_id_attr = (
                                    getattr(trunk, "inbound_trunk_id", None)
                                    or getattr(trunk, "trunk_id", None)
                                    or getattr(trunk, "id", None)
                                )
                                trunk_numbers = getattr(trunk, "numbers", [])

                                # If this trunk is for the same phone number, use it
                                if phone_number in trunk_numbers:
                                    logger.info(
                                        f"Found existing trunk for phone {phone_number}: {trunk_id_attr}. " f"Reusing it."
                                    )
                                    return trunk_id_attr or trunk_name

                        # If we can't find it, log and use the trunk_name as fallback
                        logger.warning(
                            f"Could not find existing trunk for phone {phone_number}. "
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
            # If trunk already exists, that's fine - use the trunk_name as ID
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str or "409" in error_str:
                logger.info(f"SIP trunk already exists for tenant {tenant_id}, using existing: {trunk_name}")
                return trunk_name
            else:
                logger.error(f"Failed to get or create SIP trunk for tenant {tenant_id}: {e}")
                raise Exception(f"Failed to setup SIP trunk: {str(e)}")

    async def _create_or_update_dispatch_rule(self, tenant_id: str, phone_number: str, trunk_id: str) -> str:
        """
        Create or update LiveKit dispatch rule for phone number.

        Official Documentation: https://docs.livekit.io/sip/api/#createsipdispatchrule

        Returns dispatch_rule_id.
        """
        try:
            livekit_api = self._get_livekit_api()

            # Clean phone number for rule ID (remove +, -, spaces)
            phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            rule_id = f"rule-{phone_clean}"

            # Try to check for existing rule (if API method exists)
            try:
                if hasattr(livekit_api.sip, "list_sip_dispatch_rules"):
                    rules = await livekit_api.sip.list_sip_dispatch_rules(trunk_id=trunk_id)
                    for rule in rules:
                        if rule.dispatch_rule_id == rule_id:
                            logger.info(f"Found existing dispatch rule for phone {phone_number}: {rule_id}")
                            return rule_id
            except (AttributeError, Exception) as e:
                # Method doesn't exist or error - we'll try to create
                logger.debug(f"Could not check for existing dispatch rule (may not be supported): {e}")

            # Create dispatch rule using correct API
            # Official Documentation: https://docs.livekit.io/sip/api/#createsipdispatchrule
            if not hasattr(livekit_api.sip, "create_sip_dispatch_rule"):
                logger.warning(
                    f"Dispatch rule creation not available in LiveKit SDK. "
                    f"Skipping dispatch rule - TwiML direct routing will be used instead."
                )
                return rule_id  # Return the rule_id we would have used

            # Check if rule already exists (optional check)
            try:
                if hasattr(livekit_api.sip, "list_sip_dispatch_rule"):
                    # Note: Need inbound_trunk_id to list rules, not trunk_id
                    # For now, we'll try to create and handle "already exists" errors
                    pass
            except Exception:
                pass

            # Create dispatch rule with correct request structure
            # Official Documentation: https://docs.livekit.io/sip/dispatch-rule/
            # Python example: https://docs.livekit.io/sip/dispatch-rule/#caller-dispatch-rule-individual
            # FIX: Use dispatch_rule_individual with room_prefix to match webhook room naming
            # Webhook creates rooms like: inbound-{caller_number}-{call_sid}
            # Dispatch rule should use room_prefix="inbound-" to match this pattern
            try:
                # Correct structure per documentation:
                # CreateSIPDispatchRuleRequest(
                #   dispatch_rule=SIPDispatchRuleInfo(
                #     rule=SIPDispatchRule(
                #       dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix="...")
                #     )
                #   )
                # )
                dispatch_rule = await livekit_api.sip.create_sip_dispatch_rule(
                    api.CreateSIPDispatchRuleRequest(
                        dispatch_rule=api.SIPDispatchRuleInfo(
                            rule=api.SIPDispatchRule(
                                # Use dispatch_rule_individual to create unique rooms per call
                                # This matches our webhook's dynamic room creation pattern
                                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                                    room_prefix="inbound-",  # Matches webhook room naming: inbound-{caller}-{call_sid}
                                ),
                            ),
                            name=f"Dispatch rule for {phone_number}",
                            trunk_ids=[trunk_id] if trunk_id else [],  # Associate with trunk
                        ),
                    )
                )

                # Handle different response structures
                if hasattr(dispatch_rule, "dispatch_rule_id"):
                    rule_id_result = dispatch_rule.dispatch_rule_id
                elif hasattr(dispatch_rule, "rule_id"):
                    rule_id_result = dispatch_rule.rule_id
                elif isinstance(dispatch_rule, str):
                    rule_id_result = dispatch_rule
                else:
                    rule_id_result = rule_id  # Fallback

                logger.info(f"Created dispatch rule for phone {phone_number}: {rule_id_result}")
                return rule_id_result
            except Exception as create_error:
                # If rule already exists, that's fine - use the rule_id
                error_str = str(create_error).lower()
                if "already exists" in error_str or "duplicate" in error_str or "409" in error_str:
                    logger.info(f"Dispatch rule already exists for phone {phone_number}, using existing: {rule_id}")
                    return rule_id
                else:
                    # For other errors, log and skip (non-critical)
                    # TwiML routing works without dispatch rules
                    logger.warning(
                        f"Failed to create dispatch rule (non-critical): {create_error}. "
                        f"Skipping - TwiML direct routing will work without dispatch rules."
                    )
                    return rule_id

        except Exception as e:
            logger.error(f"Failed to create dispatch rule for phone {phone_number}: {e}")
            # Return rule_id as fallback (non-critical - TwiML routing works without dispatch rules)
            return rule_id

    async def _configure_twilio_phone_webhook(self, tenant_id: str, phone_number: str) -> Dict[str, Any]:
        """
        Configure Twilio phone number webhook URLs.

        Official Documentation: https://www.twilio.com/docs/phone-numbers/api/incomingphonenumber-resource#update-an-incomingphonenumber-resource

        Returns phone number resource info.
        """
        try:
            # Get Twilio integration with decrypted auth_token
            twilio_integration = await self._get_decrypted_twilio_integration(tenant_id)
            if not twilio_integration:
                raise ValueError(f"No Twilio integration found for tenant {tenant_id}")

            # Create Twilio client
            twilio_client = Client(twilio_integration["account_sid"], twilio_integration["auth_token"])

            # Find the phone number resource
            incoming_numbers = twilio_client.incoming_phone_numbers.list(phone_number=phone_number)

            if not incoming_numbers:
                raise ValueError(f"Phone number {phone_number} not found in Twilio account")

            phone_number_resource = incoming_numbers[0]

            # Check if webhook is already configured correctly
            webhook_url = f"{TWILIO_WEBHOOK_BASE_URL}/api/v1/voice-agent/twilio/webhook"
            status_callback_url = f"{TWILIO_WEBHOOK_BASE_URL}/api/v1/voice-agent/twilio/status"

            needs_update = False
            if phone_number_resource.voice_url != webhook_url:
                needs_update = True
            if phone_number_resource.status_callback != status_callback_url:
                needs_update = True

            if needs_update:
                # Configure the phone number to use our webhook
                phone_number_resource.update(
                    voice_url=webhook_url,
                    voice_method="POST",
                    status_callback=status_callback_url,
                    status_callback_method="POST",
                )
                logger.info(f"Configured webhook for phone number {phone_number}")
            else:
                logger.info(f"Phone number {phone_number} webhook already configured correctly")

            return {
                "phone_sid": phone_number_resource.sid,
                "phone_number": phone_number_resource.phone_number,
                "voice_url": phone_number_resource.voice_url,
                "status_callback": phone_number_resource.status_callback,
            }

        except TwilioException as e:
            logger.error(f"Twilio error configuring phone number {phone_number}: {e}")
            raise Exception(f"Twilio API error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to configure phone number webhook: {e}")
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
                phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
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
            # Use phone-number-based trunk ID as fallback
            phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            return {
                "trunk_id": trunk_id or f"trunk-{phone_clean}",  # Use phone-number-based fallback
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

        Optionally removes dispatch rule. Trunk is phone-number-specific so can be kept or deleted.
        """
        try:
            if dispatch_rule_id:
                try:
                    livekit_api = self._get_livekit_api()
                    # Use phone-number-based trunk ID
                    phone_clean = (
                        phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                    )
                    trunk_id = f"trunk-{phone_clean}"

                    # Delete dispatch rule (if API method exists)
                    if hasattr(livekit_api.sip, "delete_sip_dispatch_rule"):
                        await livekit_api.sip.delete_sip_dispatch_rule(trunk_id=trunk_id, rule_id=dispatch_rule_id)
                        logger.info(f"Deleted dispatch rule {dispatch_rule_id} for phone {phone_number}")
                    else:
                        logger.warning(f"delete_sip_dispatch_rule method not available in LiveKit SDK")
                except Exception as e:
                    logger.warning(f"Failed to delete dispatch rule: {e}")
                    # Non-critical, continue

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup SIP configuration: {e}")
            return False


# Global SIP configuration service instance
sip_configuration_service = SIPConfigurationService()
