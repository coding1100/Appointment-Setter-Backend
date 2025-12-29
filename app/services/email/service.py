from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import email_settings
from app.services.email.templates import EmailTemplates
from datetime import datetime
from typing import Optional, List
import logging

class EmailService:
    def __init__(self):
        self.conf = ConnectionConfig(
            MAIL_USERNAME=email_settings.MAIL_USERNAME,
            MAIL_PASSWORD=email_settings.MAIL_PASSWORD,
            MAIL_FROM=email_settings.MAIL_FROM,
            MAIL_PORT=email_settings.MAIL_PORT,
            MAIL_SERVER=email_settings.MAIL_SERVER,
            MAIL_STARTTLS=email_settings.MAIL_STARTTLS,
            MAIL_SSL_TLS=email_settings.MAIL_SSL_TLS,
            USE_CREDENTIALS=email_settings.USE_CREDENTIALS,
            VALIDATE_CERTS=email_settings.VALIDATE_CERTS
        )
        self.fm = FastMail(self.conf)

    async def _send(self, subject: str, recipients: list[str], html_body: str):
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=html_body,
            subtype=MessageType.html
        )
        try:
            await self.fm.send_message(message)
            logging.info(f"Email sent to {recipients}")
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            raise e
            
    async def send_raw_email(self, to_email: str, subject: str, body: str) -> str:
        """
        Generic method to send an email to a specific recipient.
        Used by the AI agent tool.
        """
        try:
            # Wrap body in basic HTML if it's plain text, or trust generic_submission template
            html = EmailTemplates.generic_submission(to_email or "AI Agent User", body, "N/A")
            await self._send(subject, [to_email], html)
            return f"Email successfully sent to {to_email}"
        except Exception as e:
            return f"Failed to send email: {str(e)}"


    # --- Existing Functionality (Ported and Adapted) ---
    
    async def send_appointment_confirmation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        service_type: str,
        service_address: str,
        appointment_id: Optional[str] = None,
        service_details: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type,
                "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "service_address": service_address,
                "appointment_id": appointment_id or "N/A",
                "service_details": service_details,
                "business_name": business_name or "AI Phone Scheduler",
            }
            subject, html = EmailTemplates.appointment_confirmation(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logging.error(f"Error sending appointment confirmation email: {e}", exc_info=True)
            return False

    async def send_appointment_cancellation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        reason: Optional[str] = None,
        service_type: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type or "Service",
                "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "old_status": "scheduled",
                "new_status": "cancelled",
                "appointment_id": "N/A",
                "business_name": business_name or "AI Phone Scheduler",
                "cancellation_reason": reason,
            }
            subject, html = EmailTemplates.appointment_status_update(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logging.error(f"Error sending appointment cancellation email: {e}", exc_info=True)
            return False

    async def send_appointment_reschedule(
        self,
        customer_email: str,
        customer_name: str,
        new_datetime: datetime,
        reason: Optional[str] = None,
        old_datetime: Optional[datetime] = None,
        service_type: Optional[str] = None,
        service_address: Optional[str] = None,
        appointment_id: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> bool:
        try:
            data = {
                "customer_name": customer_name,
                "service_type": service_type or "Service",
                "old_datetime": old_datetime.strftime("%B %d, %Y at %I:%M %p") if old_datetime else "N/A",
                "new_datetime": new_datetime.strftime("%B %d, %Y at %I:%M %p"),
                "service_address": service_address or "N/A",
                "appointment_id": appointment_id or "N/A",
                "business_name": business_name or "AI Phone Scheduler",
                "reschedule_reason": reason,
            }
            subject, html = EmailTemplates.appointment_reschedule(data)
            await self._send(subject, [customer_email], html)
            return True
        except Exception as e:
            logging.error(f"Error sending appointment reschedule email: {e}", exc_info=True)
            return False
