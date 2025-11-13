"""
Phone number management API routes.
"""

from typing import List

from fastapi import APIRouter, HTTPException, status

from app.api.v1.schemas.phone_number import AgentPhoneAssignment, PhoneNumberCreate, PhoneNumberResponse, PhoneNumberUpdate
from app.api.v1.services.phone_number import phone_number_service

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])


@router.post("/tenant/{tenant_id}", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def create_phone_number(tenant_id: str, phone_data: PhoneNumberCreate):
    """
    Create a new phone number assignment.

    - **tenant_id**: ID of the tenant
    - **phone_data**: Phone number assignment data
    """
    try:
        phone = await phone_number_service.create_phone_number(tenant_id, phone_data)
        return PhoneNumberResponse(**phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create phone number assignment: {str(e)}"
        )


@router.get("/tenant/{tenant_id}", response_model=List[PhoneNumberResponse])
async def list_phone_numbers(tenant_id: str):
    """
    List all phone numbers for a tenant.

    - **tenant_id**: ID of the tenant
    """
    try:
        phones = await phone_number_service.list_phones_by_tenant(tenant_id)
        return [PhoneNumberResponse(**phone) for phone in phones]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list phone numbers: {str(e)}"
        )


@router.get("/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(phone_id: str):
    """
    Get phone number by ID.

    - **phone_id**: ID of the phone number
    """
    try:
        phone = await phone_number_service.get_phone_number(phone_id)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
        return PhoneNumberResponse(**phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get phone number: {str(e)}")


@router.get("/agent/{agent_id}", response_model=PhoneNumberResponse)
async def get_phone_by_agent(agent_id: str):
    """
    Get phone number assigned to an agent.

    - **agent_id**: ID of the agent
    """
    try:
        phone = await phone_number_service.get_phone_by_agent(agent_id)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number assigned to this agent")
        return PhoneNumberResponse(**phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get phone number for agent: {str(e)}"
        )


@router.put("/{phone_id}", response_model=PhoneNumberResponse)
async def update_phone_number(phone_id: str, phone_data: PhoneNumberUpdate):
    """
    Update phone number assignment.

    - **phone_id**: ID of the phone number
    - **phone_data**: Updated phone number data
    """
    try:
        phone = await phone_number_service.update_phone_number(phone_id, phone_data)
        if not phone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
        return PhoneNumberResponse(**phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update phone number: {str(e)}"
        )


@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number(phone_id: str):
    """
    Delete phone number assignment.

    - **phone_id**: ID of the phone number
    """
    try:
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
async def assign_phone_to_agent(tenant_id: str, assignment: AgentPhoneAssignment):
    """
    Assign a phone number to an agent.

    This endpoint creates a new phone number assignment or updates an existing one.

    - **tenant_id**: ID of the tenant
    - **assignment**: Agent and phone number assignment data
    """
    try:
        # Get twilio integration for this tenant
        from app.services.firebase import firebase_service

        twilio_integration = await firebase_service.get_twilio_integration(tenant_id)

        if not twilio_integration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twilio integration not configured for this tenant. Please add Twilio credentials first.",
            )

        phone = await phone_number_service.assign_phone_to_agent(
            tenant_id=tenant_id,
            agent_id=assignment.agent_id,
            phone_number=assignment.phone_number,
            twilio_integration_id=twilio_integration["id"],
        )
        return PhoneNumberResponse(**phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to assign phone number: {str(e)}"
        )


@router.delete("/agent/{agent_id}/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_phone_from_agent(agent_id: str):
    """
    Remove phone number assignment from an agent.

    - **agent_id**: ID of the agent
    """
    try:
        success = await phone_number_service.unassign_phone_from_agent(agent_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number assigned to this agent")
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to unassign phone number: {str(e)}"
        )
