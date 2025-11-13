"""
API v1 router configuration.
"""
from fastapi import APIRouter
from app.api.v1.routers import (
    auth,
    tenants,
    appointments,
    voice_agent_unified,
    twilio_integration,
    health,
    agents,
    phone_numbers
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
