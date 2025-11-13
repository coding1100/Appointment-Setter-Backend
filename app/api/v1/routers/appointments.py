"""
Appointment management API routes using Firebase.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.services.appointment import appointment_service
from app.api.v1.services.auth import auth_service
from app.api.v1.services.scheduling import scheduling_service
from app.core.security import SecurityService

router = APIRouter(prefix="/appointments", tags=["appointments"])


def get_security_service() -> SecurityService:
    """Get security service instance."""
    return SecurityService()


@router.post("/")
async def create_appointment(
    tenant_id: str,
    customer_name: str,
    customer_phone: str,
    customer_email: Optional[str],
    service_type: str,
    service_address: str,
    appointment_datetime: datetime,
    service_details: Optional[str] = None,
    duration_minutes: int = 60,
):
    """Create a new appointment."""
    try:
        appointment = await appointment_service.create_appointment(
            tenant_id=tenant_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            service_type=service_type,
            service_address=service_address,
            appointment_datetime=appointment_datetime,
            service_details=service_details,
            duration_minutes=duration_minutes,
        )

        if not appointment:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create appointment")

        return {"message": "Appointment created successfully", "appointment": appointment}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create appointment: {str(e)}"
        )


@router.get("/{appointment_id}")
async def get_appointment(appointment_id: str):
    """Get appointment by ID."""
    try:
        appointment = await appointment_service.get_appointment(appointment_id)
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return appointment

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get appointment: {str(e)}")


@router.get("/tenant/{tenant_id}")
async def list_appointments(
    tenant_id: str,
    status: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List appointments for a tenant."""
    try:
        # Convert date to datetime for filtering
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        appointments = await appointment_service.list_appointments(
            tenant_id=tenant_id, status=status, start_date=start_datetime, end_date=end_datetime, limit=limit, offset=offset
        )

        return {"appointments": appointments, "total": len(appointments), "limit": limit, "offset": offset}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list appointments: {str(e)}")


@router.put("/{appointment_id}/status")
async def update_appointment_status(appointment_id: str, status: str, notes: Optional[str] = None):
    """Update appointment status."""
    try:
        appointment = await appointment_service.update_appointment_status(appointment_id, status, notes)

        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return {"message": "Appointment status updated successfully", "appointment": appointment}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update appointment status: {str(e)}"
        )


@router.put("/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str, reason: Optional[str] = None):
    """Cancel an appointment."""
    try:
        appointment = await appointment_service.cancel_appointment(appointment_id, reason)

        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return {"message": "Appointment cancelled successfully", "appointment": appointment}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to cancel appointment: {str(e)}"
        )


@router.put("/{appointment_id}/reschedule")
async def reschedule_appointment(appointment_id: str, new_datetime: datetime, reason: Optional[str] = None):
    """Reschedule an appointment."""
    try:
        appointment = await appointment_service.reschedule_appointment(appointment_id, new_datetime, reason)

        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return {"message": "Appointment rescheduled successfully", "appointment": appointment}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reschedule appointment: {str(e)}"
        )


@router.put("/{appointment_id}/complete")
async def complete_appointment(appointment_id: str, completion_notes: Optional[str] = None):
    """Mark appointment as completed."""
    try:
        appointment = await appointment_service.complete_appointment(appointment_id, completion_notes)

        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return {"message": "Appointment completed successfully", "appointment": appointment}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to complete appointment: {str(e)}"
        )


@router.get("/tenant/{tenant_id}/upcoming")
async def get_upcoming_appointments(tenant_id: str, days_ahead: int = Query(7, ge=1, le=30)):
    """Get upcoming appointments for a tenant."""
    try:
        appointments = await appointment_service.get_upcoming_appointments(tenant_id, days_ahead)

        return {"appointments": appointments, "days_ahead": days_ahead, "total": len(appointments)}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get upcoming appointments: {str(e)}"
        )


@router.get("/tenant/{tenant_id}/date-range")
async def get_appointments_by_date_range(tenant_id: str, start_date: date, end_date: date):
    """Get appointments within a date range."""
    try:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        appointments = await appointment_service.get_appointments_by_date_range(tenant_id, start_datetime, end_datetime)

        return {
            "appointments": appointments,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total": len(appointments),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get appointments by date range: {str(e)}"
        )


@router.get("/tenant/{tenant_id}/available-slots")
async def get_available_slots(tenant_id: str, target_date: date, duration_minutes: int = Query(60, ge=15, le=480)):
    """Get available time slots for a specific date."""
    try:
        slots = await scheduling_service.get_available_slots_for_date(tenant_id, target_date, duration_minutes)

        return {
            "date": target_date.isoformat(),
            "duration_minutes": duration_minutes,
            "slots": [
                {
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "duration_minutes": slot.duration_minutes,
                    "is_available": slot.is_available,
                    "is_held": slot.is_held,
                }
                for slot in slots
            ],
            "total_slots": len(slots),
            "available_slots": len([s for s in slots if s.is_available]),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get available slots: {str(e)}"
        )


@router.post("/tenant/{tenant_id}/hold-slot")
async def hold_slot(
    tenant_id: str,
    slot_start: datetime,
    slot_end: datetime,
    customer_name: str,
    customer_phone: str,
    hold_duration_minutes: int = Query(10, ge=5, le=30),
):
    """Hold a time slot for a customer."""
    try:
        hold_id = await scheduling_service.hold_slot(
            tenant_id, slot_start, slot_end, customer_name, customer_phone, hold_duration_minutes
        )

        if not hold_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to hold slot")

        return {"message": "Slot held successfully", "hold_id": hold_id, "expires_in_minutes": hold_duration_minutes}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to hold slot: {str(e)}")


@router.delete("/hold/{hold_id}")
async def release_slot_hold(hold_id: str):
    """Release a slot hold."""
    try:
        success = await scheduling_service.release_slot_hold(hold_id)

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot hold not found")

        return {"message": "Slot hold released successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to release slot hold: {str(e)}")
