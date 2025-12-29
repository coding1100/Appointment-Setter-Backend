from datetime import datetime
from typing import Dict, List, Any

class EmailTemplates:
    
    @staticmethod
    def generic_submission(email: str, message: str, phone_number: str) -> str:
        return f"""
        <div>
            <div>Email: {email or "NOT_PROVIDED"} </div>
            <br>
            <div>Message: {message or "NOT_PROVIDED"}</div>
            <br>
            <div>Phone Number: {phone_number or "NOT_PROVIDED"}</div>
        </div>
        """


    # --- Appointment Templates (Ported) ---

    @staticmethod
    def _create_html_wrapper(title: str, content: str, header_color: str = "#4CAF50") -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {header_color}; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .details-box {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                </div>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def appointment_confirmation(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"Appointment Confirmed - {data.get('service_type', 'Service')}"
        content = f"""
            <p>Dear {data.get('customer_name', 'Customer')},</p>
            <p>Your appointment has been successfully confirmed. Here are the details:</p>
            
            <div class="details-box">
                <h3>Appointment Details</h3>
                <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                {f"<p><strong>Details:</strong> {data.get('service_details', '')}</p>" if data.get('service_details') else ""}
                <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
            </div>
            
            <p>If you need to reschedule or cancel this appointment, please contact us as soon as possible.</p>
            <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
        """
        return subject, EmailTemplates._create_html_wrapper("Appointment Confirmed!", content)

    @staticmethod
    def appointment_owner_notification(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"New Appointment Confirmed - {data.get('service_type', 'Service')}"
        content = f"""
            <p>Hello,</p>
            <p>A new appointment has been confirmed. Here are the details:</p>
            
            <div class="details-box">
                <h3>Appointment Details</h3>
                <p><strong>Customer Name:</strong> {data.get('customer_name', 'N/A')}</p>
                <p><strong>Customer Email:</strong> {data.get('customer_email', 'N/A')}</p>
                <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                {f"<p><strong>Details:</strong> {data.get('service_details', '')}</p>" if data.get('service_details') else ""}
                <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
            </div>
            
            <p>This is an automated message for your records.</p>
        """
        return subject, EmailTemplates._create_html_wrapper("New Appointment Confirmed", content, header_color="#1976D2")

    @staticmethod
    def appointment_status_update(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"Appointment Status Update - {data.get('service_type', 'Service')}"
        content = f"""
            <p>Dear {data.get('customer_name', 'Customer')},</p>
            <p>Your appointment status has been updated:</p>
            
            <div class="details-box">
                <h3>Status Change</h3>
                <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                <p><strong>Date & Time:</strong> {data.get('appointment_datetime', 'N/A')}</p>
                <p><strong>Previous Status:</strong> {data.get('old_status', 'N/A')}</p>
                <p><strong>New Status:</strong> {data.get('new_status', 'N/A')}</p>
                <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                {f"<p><strong>Reason:</strong> {data.get('cancellation_reason', '')}</p>" if data.get('cancellation_reason') else ""}
            </div>
            
            <p>If you have any questions about this status change, please contact us.</p>
            <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
        """
        return subject, EmailTemplates._create_html_wrapper("Appointment Status Update", content, header_color="#2196F3")

    @staticmethod
    def appointment_reschedule(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"Appointment Rescheduled - {data.get('service_type', 'Service')}"
        content = f"""
            <p>Dear {data.get('customer_name', 'Customer')},</p>
            <p>Your appointment has been rescheduled. Here are the updated details:</p>
            
            <div class="details-box">
                <h3>Updated Appointment Details</h3>
                <p><strong>Service:</strong> {data.get('service_type', 'N/A')}</p>
                <p><strong>Previous Date & Time:</strong> {data.get('old_datetime', 'N/A')}</p>
                <p><strong>New Date & Time:</strong> {data.get('new_datetime', 'N/A')}</p>
                <p><strong>Address:</strong> {data.get('service_address', 'N/A')}</p>
                <p><strong>Appointment ID:</strong> {data.get('appointment_id', 'N/A')}</p>
                {f"<p><strong>Reason:</strong> {data.get('reschedule_reason', '')}</p>" if data.get('reschedule_reason') else ""}
            </div>
            
            <p>If you need to make any further changes to this appointment, please contact us as soon as possible.</p>
            <p>Thank you for choosing {data.get('business_name', 'our services')}!</p>
        """
        return subject, EmailTemplates._create_html_wrapper("Appointment Rescheduled", content, header_color="#FF9800")
