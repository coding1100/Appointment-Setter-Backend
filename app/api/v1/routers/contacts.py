"""
Contact/Lead submission API routes.
"""

import uuid
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, HTTPException, status

from app.api.v1.schemas.contact import ContactCreate, ContactResponse

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(contact_data: ContactCreate):
    """
    Create a new contact/lead submission.

    At least one of email or phone_number must be provided.
    Both fields are optional, but at least one is required.
    """
    try:
        # Generate a unique ID for the contact
        contact_id = uuid.uuid4()

        # Create contact record
        contact = {
            "id": str(contact_id),
            "email": contact_data.email,
            "phone_number": contact_data.phone_number,
            "created_at": datetime.utcnow().isoformat(),
        }

        # TODO: Save to database (Firebase Firestore)
        # For now, we'll just return the contact data
        # Example: await contact_service.create_contact(contact_data)

        return ContactResponse(
            id=contact_id,
            email=contact_data.email,
            phone_number=contact_data.phone_number,
            created_at=datetime.utcnow(),
        )

    except ValueError as e:
        # Handle validation errors from Pydantic
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create contact: {str(e)}")

