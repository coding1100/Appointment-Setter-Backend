"""
Email service for SendGrid integration and email templates.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

from app.core.config import SENDGRID_API_KEY, SENDGRID_FROM_EMAIL

# Configure logging
logger = logging.getLogger(__name__)

class EmailService:
    """Service class for email operations using SendGrid."""
    
    def __init__(self):
        self.sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        self.from_email = SENDGRID_FROM_EMAIL
    
    def send_email(self, email_data: Dict[str, Any]) -> bool:
        """Send email using SendGrid."""
        try:
            to_email = email_data["to_email"]
            template_name = email_data["template_name"]
            template_data = email_data.get("template_data", {})
            
            # Get email template
            subject, html_content = self._get_email_template(template_name, template_data)
            
            # Create email
            from_email = Email(self.from_email)
            to_email = To(to_email)
            content = HtmlContent(html_content)
            
            mail = Mail(from_email, to_email, subject, content)
            
            # Send email
            response = self.sg.send(mail)
            
            return response.status_code in [200, 201, 202]
            
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return False
    
    def _get_email_template(self, template_name: str, template_data: Dict[str, Any]) -> tuple[str, str]:
        """Get email template content."""
        templates = {
            "appointment_confirmation": self._appointment_confirmation_template,
            "appointment_status_update": self._appointment_status_update_template,
            "appointment_reschedule": self._appointment_reschedule_template,
            "tenant_appointment_notification": self._tenant_appointment_notification_template,
            "password_reset": self._password_reset_template,
            "email_verification": self._email_verification_template,
            "welcome": self._welcome_template
        }
        
        template_func = templates.get(template_name)
        if not template_func:
            raise ValueError(f"Unknown email template: {template_name}")
        
        return template_func(template_data)
    
    def _appointment_confirmation_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Appointment confirmation email template."""
        subject = f"Appointment Confirmed - {data.get('service_type', 'Service')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Appointment Confirmation</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .appointment-details {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Appointment Confirmed!</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'Customer')},</p>
                    <p>Your appointment has been successfully confirmed. Here are the details:</p>
                    
                    <div class="appointment-details">
                        <h3>Appointment Details</h3>
                        <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                        <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                        <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                        {f"<p><strong>Details:</strong> {data.get('service_details', '')}</p>" if data.get('service_details') else ""}
                        <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                    </div>
                    
                    <p>If you need to reschedule or cancel this appointment, please contact us as soon as possible.</p>
                    <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _appointment_status_update_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Appointment status update email template."""
        subject = f"Appointment Status Update - {data.get('service_type', 'Service')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Appointment Status Update</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .status-change {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Appointment Status Update</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'Customer')},</p>
                    <p>Your appointment status has been updated:</p>
                    
                    <div class="status-change">
                        <h3>Status Change</h3>
                        <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                        <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                        <p><strong>Previous Status:</strong> {data.get('old_status', 'N/A')}</p>
                        <p><strong>New Status:</strong> {data.get('new_status', 'N/A')}</p>
                        <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                    </div>
                    
                    <p>If you have any questions about this status change, please contact us.</p>
                    <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _appointment_reschedule_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Appointment reschedule email template."""
        subject = f"Appointment Rescheduled - {data.get('service_type', 'Service')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Appointment Rescheduled</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #FF9800; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .reschedule-details {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Appointment Rescheduled</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'Customer')},</p>
                    <p>Your appointment has been rescheduled. Here are the updated details:</p>
                    
                    <div class="reschedule-details">
                        <h3>Updated Appointment Details</h3>
                        <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                        <p><strong>Previous Date & Time:</strong> {data.get('old_datetime', 'N/A')}</p>
                        <p><strong>New Date & Time:</strong> {data.get('new_datetime', 'N/A')}</p>
                        <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                        <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                    </div>
                    
                    <p>If you need to make any further changes to this appointment, please contact us as soon as possible.</p>
                    <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _tenant_appointment_notification_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Tenant appointment notification email template."""
        subject = f"New Appointment Booking - {data.get('service_type', 'Service')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>New Appointment Booking</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #9C27B0; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .appointment-details {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .customer-info {{ background-color: #e8f5e8; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Appointment Booking</h1>
                </div>
                <div class="content">
                    <p>You have received a new appointment booking:</p>
                    
                    <div class="appointment-details">
                        <h3>Appointment Details</h3>
                        <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                        <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                        <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                        {f"<p><strong>Details:</strong> {data.get('service_details', '')}</p>" if data.get('service_details') else ""}
                        <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                    </div>
                    
                    <div class="customer-info">
                        <h3>Customer Information</h3>
                        <p><strong>Name:</strong> {data.get('customer_name', 'N/A')}</p>
                        <p><strong>Phone:</strong> {data.get('customer_phone', 'N/A')}</p>
                        <p><strong>Email:</strong> {data.get('customer_email', 'N/A')}</p>
                    </div>
                    
                    <p>Please prepare for this appointment and contact the customer if needed.</p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from your appointment booking system.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _password_reset_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Password reset email template."""
        subject = "Password Reset Request"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #F44336; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .reset-button {{ background-color: #F44336; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'User')},</p>
                    <p>You have requested to reset your password. Click the button below to reset your password:</p>
                    
                    <div style="text-align: center;">
                        <a href="{data.get('reset_url', '#')}" class="reset-button">Reset Password</a>
                    </div>
                    
                    <p>This link will expire in 1 hour for security reasons.</p>
                    <p>If you did not request this password reset, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _email_verification_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Email verification template."""
        subject = "Verify Your Email Address"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Email Verification</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .verify-button {{ background-color: #4CAF50; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome!</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'User')},</p>
                    <p>Thank you for registering! Please verify your email address by clicking the button below:</p>
                    
                    <div style="text-align: center;">
                        <a href="{data.get('verification_url', '#')}" class="verify-button">Verify Email</a>
                    </div>
                    
                    <p>If you did not create an account, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def _welcome_template(self, data: Dict[str, Any]) -> tuple[str, str]:
        """Welcome email template."""
        subject = "Welcome to AI Phone Scheduler!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome!</h1>
                </div>
                <div class="content">
                    <p>Dear {data.get('customer_name', 'User')},</p>
                    <p>Welcome to AI Phone Scheduler! Your account has been successfully created.</p>
                    <p>You can now start booking appointments and managing your schedule.</p>
                    <p>If you have any questions, please don't hesitate to contact our support team.</p>
                </div>
                <div class="footer">
                    <p>Thank you for choosing AI Phone Scheduler!</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    # Public async methods for appointment emails
    
    async def send_appointment_confirmation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        service_type: str,
        service_address: str,
        appointment_id: Optional[str] = None,
        service_details: Optional[str] = None,
        business_name: Optional[str] = None
    ) -> bool:
        """Send appointment confirmation email to customer."""
        try:
            email_data = {
                "to_email": customer_email,
                "template_name": "appointment_confirmation",
                "template_data": {
                    "customer_name": customer_name,
                    "service_type": service_type,
                    "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                    "service_address": service_address,
                    "appointment_id": appointment_id or "N/A",
                    "service_details": service_details,
                    "business_name": business_name or "AI Phone Scheduler"
                }
            }
            return self.send_email(email_data)
        except Exception as e:
            logger.error(f"Error sending appointment confirmation email: {e}", exc_info=True)
            return False
    
    async def send_appointment_cancellation(
        self,
        customer_email: str,
        customer_name: str,
        appointment_datetime: datetime,
        reason: Optional[str] = None,
        service_type: Optional[str] = None,
        business_name: Optional[str] = None
    ) -> bool:
        """Send appointment cancellation email to customer."""
        try:
            email_data = {
                "to_email": customer_email,
                "template_name": "appointment_status_update",
                "template_data": {
                    "customer_name": customer_name,
                    "service_type": service_type or "Service",
                    "appointment_datetime": appointment_datetime.strftime("%B %d, %Y at %I:%M %p"),
                    "old_status": "scheduled",
                    "new_status": "cancelled",
                    "appointment_id": "N/A",
                    "business_name": business_name or "AI Phone Scheduler",
                    "cancellation_reason": reason
                }
            }
            return self.send_email(email_data)
        except Exception as e:
            logger.error(f"Error sending appointment cancellation email: {e}", exc_info=True)
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
        business_name: Optional[str] = None
    ) -> bool:
        """Send appointment reschedule email to customer."""
        try:
            email_data = {
                "to_email": customer_email,
                "template_name": "appointment_reschedule",
                "template_data": {
                    "customer_name": customer_name,
                    "service_type": service_type or "Service",
                    "old_datetime": old_datetime.strftime("%B %d, %Y at %I:%M %p") if old_datetime else "N/A",
                    "new_datetime": new_datetime.strftime("%B %d, %Y at %I:%M %p"),
                    "service_address": service_address or "N/A",
                    "appointment_id": appointment_id or "N/A",
                    "business_name": business_name or "AI Phone Scheduler",
                    "reschedule_reason": reason
                }
            }
            return self.send_email(email_data)
        except Exception as e:
            logger.error(f"Error sending appointment reschedule email: {e}", exc_info=True)
            return False