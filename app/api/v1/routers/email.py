from fastapi import APIRouter
from app.services.email.service import EmailService

router = APIRouter()
email_service = EmailService()

@router.get("/")
async def email_health():
    return {"status": "Email service active"}
