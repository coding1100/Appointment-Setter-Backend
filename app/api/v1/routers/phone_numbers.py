"""
Phone number management API routes.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.routers.auth import get_current_user_from_token, verify_tenant_access
from app.api.v1.schemas.phone_number import AgentPhoneAssignment, PhoneNumberCreate, PhoneNumberResponse, PhoneNumberUpdate
from app.api.v1.services.phone_number import phone_number_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])


@router.post("/tenant/{tenant_id}", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def create_phone_number(
    tenant_id: str, phone_data: PhoneNumberCreate, current_user: Dict = Depends(get_current_user_from_token)
):
    """
    Create a new phone number assignment.

    - **tenant_id**: ID of the tenant
    - **phone_data**: Phone number assignment data
    """
    verify_tenant_access(current_user, tenant_id)
    try:
        phone = await phone_number_service.create_phone_number(tenant_id, phone_data)
        from app.core.response_mappers import to_phone_number_response
        return to_phone_number_response(phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create phone number assignment: {str(e)}"
        )


@router.get("/tenant/{tenant_id}", response_model=List[PhoneNumberResponse])
async def list_phone_numbers(tenant_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """
    List all phone numbers for a tenant.

    - **tenant_id**: ID of the tenant
    """
    verify_tenant_access(current_user, tenant_id)
    try:
        phones = await phone_number_service.list_phones_by_tenant(tenant_id)
        from app.core.response_mappers import to_phone_number_response
        return [to_phone_number_response(phone) for phone in phones]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list phone numbers: {str(e)}"
        )


@router.get("/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(phone_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """
    Get phone number by ID.

    - **phone_id**: ID of the phone number
    """
    try:
        phone = await phone_number_service.get_phone_number(phone_id)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
        verify_tenant_access(current_user, phone.get("tenant_id"))
        from app.core.response_mappers import to_phone_number_response
        return to_phone_number_response(phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get phone number: {str(e)}")


@router.get("/agent/{agent_id}", response_model=PhoneNumberResponse)
async def get_phone_by_agent(agent_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """
    Get phone number assigned to an agent.

    - **agent_id**: ID of the agent
    """
    try:
        phone = await phone_number_service.get_phone_by_agent(agent_id)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number assigned to this agent")
        verify_tenant_access(current_user, phone.get("tenant_id"))
        from app.core.response_mappers import to_phone_number_response
        return to_phone_number_response(phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get phone number for agent: {str(e)}"
        )


@router.put("/{phone_id}", response_model=PhoneNumberResponse)
async def update_phone_number(
    phone_id: str, phone_data: PhoneNumberUpdate, current_user: Dict = Depends(get_current_user_from_token)
):
    """
    Update phone number assignment.

    - **phone_id**: ID of the phone number
    - **phone_data**: Updated phone number data
    """
    try:
        phone = await phone_number_service.get_phone_number(phone_id)
        if phone:
            verify_tenant_access(current_user, phone.get("tenant_id"))
        phone = await phone_number_service.update_phone_number(phone_id, phone_data)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
        from app.core.response_mappers import to_phone_number_response
        return to_phone_number_response(phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update phone number: {str(e)}"
        )


@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number(phone_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """
    Delete phone number assignment.

    - **phone_id**: ID of the phone number
    """
    try:
        phone = await phone_number_service.get_phone_number(phone_id)
        if phone:
            verify_tenant_access(current_user, phone.get("tenant_id"))
        success = await phone_number_service.delete_phone_number(phone_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete phone number: {str(e)}"
        )


@router.post("/tenant/{tenant_id}/assign", response_model=PhoneNumberResponse)
async def assign_phone_to_agent(
    tenant_id: str, assignment: AgentPhoneAssignment, current_user: Dict = Depends(get_current_user_from_token)
):
    """
    Assign a phone number to an agent.

    This endpoint creates a new phone number assignment or updates an existing one.
    It automatically configures SIP infrastructure (LiveKit trunk, dispatch rules, Twilio webhooks).

    - **tenant_id**: ID of the tenant
    - **assignment**: Agent and phone number assignment data
    """
    verify_tenant_access(current_user, tenant_id)
    try:
        # Get twilio integration for this tenant
        from app.api.v1.services.sip_configuration import sip_configuration_service
        from app.services.firebase import firebase_service

        twilio_integration = await firebase_service.get_twilio_integration(tenant_id)

        if not twilio_integration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twilio integration not configured for this tenant. Please add Twilio credentials first.",
            )

        # Step 1: Assign phone to agent in database
        phone = await phone_number_service.assign_phone_to_agent(
            tenant_id=tenant_id,
            agent_id=assignment.agent_id,
            phone_number=assignment.phone_number,
            twilio_integration_id=twilio_integration["id"],
        )

        # Step 2: Setup SIP infrastructure (LiveKit + Twilio)
        try:
            sip_config = await sip_configuration_service.setup_phone_number_sip(
                tenant_id=tenant_id,
                phone_number=assignment.phone_number,
                agent_id=assignment.agent_id,
            )

            # Step 3: Store SIP configuration in phone number record
            update_data = {
                "sip_trunk_id": sip_config.get("trunk_id"),
                "sip_dispatch_rule_id": sip_config.get("dispatch_rule_id"),
                "sip_configured": True,
                "sip_configured_at": datetime.now(timezone.utc).isoformat(),
            }
            await firebase_service.update_phone_number(phone["id"], update_data)

            logger.info(
                f"Successfully assigned phone {assignment.phone_number} to agent {assignment.agent_id} with SIP configuration"
            )

        except Exception as sip_error:
            # Rollback: Remove phone assignment if SIP setup fails
            logger.error(f"SIP configuration failed, rolling back phone assignment: {sip_error}")
            try:
                await phone_number_service.delete_phone_number(phone["id"])
            except Exception as rollback_error:
                logger.error(f"Failed to rollback phone assignment: {rollback_error}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to configure SIP infrastructure: {str(sip_error)}. Phone assignment was not completed.",
            )

        from app.core.response_mappers import to_phone_number_response
        return to_phone_number_response(phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to assign phone number: {str(e)}"
        )


@router.delete("/agent/{agent_id}/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_phone_from_agent(agent_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    """
    Remove phone number assignment from an agent.

    This will also cleanup SIP dispatch rules if configured.

    - **agent_id**: ID of the agent
    """
    try:
        # Get phone number before deletion to cleanup SIP config
        phone = await phone_number_service.get_phone_by_agent(agent_id)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number assigned to this agent")
        verify_tenant_access(current_user, phone.get("tenant_id"))

        # Delete phone assignment
        success = await phone_number_service.unassign_phone_from_agent(agent_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number assigned to this agent")

        # Cleanup SIP dispatch rule if configured
        if phone.get("sip_dispatch_rule_id") and phone.get("tenant_id"):
            try:
                from app.api.v1.services.sip_configuration import sip_configuration_service

                await sip_configuration_service.cleanup_phone_number_sip(
                    tenant_id=phone["tenant_id"],
                    phone_number=phone["phone_number"],
                    dispatch_rule_id=phone.get("sip_dispatch_rule_id"),
                )
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup SIP configuration: {cleanup_error}")
                # Non-critical, continue

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to unassign phone number: {str(e)}"
        )
