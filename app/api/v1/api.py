"""
API v1 router configuration.
"""

from fastapi import APIRouter

from app.api.v1.routers import (
    agents,
    appointments,
    auth,
    contacts,
    health,
    phone_numbers,
    tenants,
    twilio_integration,
    voice_agent_unified,
    email,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(agents.router)
api_router.include_router(phone_numbers.router)
api_router.include_router(appointments.router)
api_router.include_router(voice_agent_unified.router)
api_router.include_router(twilio_integration.router)
api_router.include_router(contacts.router)
api_router.include_router(email.router)
