from html import escape as _esc
from typing import Any, Dict

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

    @staticmethod
    def partner_owner_invite(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"Welcome to {data.get('platform_name', 'MindRind')} - Set Your Password"
        content = f"""
            <p>Hello {data.get('owner_name', 'there')},</p>
            <p>Your partner workspace <strong>{data.get('partner_name', 'Partner')}</strong> is ready.</p>
            <p>To activate your account, set your password using the secure link below:</p>
            <div class="details-box">
                <p><a href="{data.get('setup_password_url', '#')}" target="_blank" rel="noopener">Set password</a></p>
                <p><strong>Login Email:</strong> {data.get('owner_email', 'N/A')}</p>
                <p><strong>Link Expiry:</strong> {data.get('expires_in_hours', 48)} hours</p>
            </div>
            <p>If the button/link doesn't open, copy and paste this URL in your browser:</p>
            <p>{data.get('setup_password_url', '#')}</p>
            <p>After setting your password, sign in here:</p>
            <p><a href="{data.get('login_url', '#')}" target="_blank" rel="noopener">{data.get('login_url', '#')}</a></p>
        """
        return subject, EmailTemplates._create_html_wrapper("Partner Onboarding", content, header_color="#0f172a")

    @staticmethod
    def user_setup_invite(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"Welcome to {data.get('platform_name', 'MindRind')} - Activate Your Account"
        content = f"""
            <p>Hello {data.get('recipient_name', 'there')},</p>
            <p>You were added to <strong>{data.get('workspace_name', 'your workspace')}</strong>.</p>
            <p>Set your password to activate your account:</p>
            <div class="details-box">
                <p><a href="{data.get('setup_password_url', '#')}" target="_blank" rel="noopener">Set password</a></p>
                <p><strong>Login Email:</strong> {data.get('recipient_email', 'N/A')}</p>
                <p><strong>Link Expiry:</strong> {data.get('expires_in_hours', 48)} hours</p>
            </div>
            <p>If needed, paste this URL in your browser:</p>
            <p>{data.get('setup_password_url', '#')}</p>
            <p>Login URL: <a href="{data.get('login_url', '#')}" target="_blank" rel="noopener">{data.get('login_url', '#')}</a></p>
        """
        return subject, EmailTemplates._create_html_wrapper("Account Invitation", content, header_color="#0f172a")

    @staticmethod
    def password_reset(data: Dict[str, Any]) -> tuple[str, str]:
        subject = f"{data.get('platform_name', 'MindRind')} Password Reset"
        content = f"""
            <p>Hello {data.get('recipient_name', 'there')},</p>
            <p>We received a request to reset your password.</p>
            <div class="details-box">
                <p><a href="{data.get('reset_password_url', '#')}" target="_blank" rel="noopener">Reset password</a></p>
                <p><strong>Link Expiry:</strong> {data.get('expires_in_minutes', 60)} minutes</p>
            </div>
            <p>If you did not request this, you can ignore this email.</p>
            <p>Direct URL:</p>
            <p>{data.get('reset_password_url', '#')}</p>
        """
        return subject, EmailTemplates._create_html_wrapper("Password Reset", content, header_color="#1d4ed8")


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
    def lead_notification(data: Dict[str, Any]) -> tuple[str, str]:
        """Generic new-lead notification — works for any voice agent.

        `data` keys (all strings, missing/empty handled gracefully):
            customer_name, customer_phone, customer_email
            summary       — one-line headline of the lead
            details       — multi-line free-form body, newlines preserved
            agent_name    — which agent took the call (e.g. "Lisa")
            service_type  — agent's vertical (e.g. "Scholarly Help")
            tenant_name   — workspace name
            call_id       — internal call id
            captured_at   — ISO 8601 timestamp

        All user-supplied values are HTML-escaped before interpolation.
        Subject is deterministically built from `service_type`, `agent_name`,
        and `summary` so operators can inbox-filter without touching code.
        """
        name = _esc(str(data.get("customer_name", "")).strip() or "Unknown")
        phone = _esc(str(data.get("customer_phone", "")).strip() or "(not provided)")
        email = _esc(str(data.get("customer_email", "")).strip() or "(not provided)")
        summary = str(data.get("summary", "")).strip() or "(no summary)"
        summary_esc = _esc(summary)
        details_raw = str(data.get("details", "")).strip()
        agent_name = str(data.get("agent_name", "")).strip()
        service_type = str(data.get("service_type", "")).strip()
        tenant_name = _esc(str(data.get("tenant_name", "")).strip() or "—")
        call_id = _esc(str(data.get("call_id", "")).strip() or "n/a")
        captured_at = _esc(str(data.get("captured_at", "")).strip() or "n/a")

        # Subject layers: [vertical] from <agent>: <summary>
        prefix = f"[{service_type}] " if service_type else ""
        attribution = f"New lead from {agent_name}" if agent_name else "New lead"
        subject = f"{prefix}{attribution}: {summary}"

        # Phone -> tel: link, preserving raw digits/+ for href.
        phone_for_href = "".join(ch for ch in str(data.get("customer_phone", "")) if ch.isdigit() or ch == "+")
        phone_href = f"tel:{phone_for_href}" if phone_for_href else "#"

        # Preserve newlines + spacing in details using <pre> with wrapping.
        if details_raw:
            details_html = (
                f'<pre style="white-space:pre-wrap; font-family:inherit; margin:0;">'
                f'{_esc(details_raw)}</pre>'
            )
        else:
            details_html = '<em>(none captured)</em>'

        header_title = f"New Lead — {service_type}" if service_type else "New Lead"

        content = f"""
            <p style="margin-top:0;">
                <strong>{_esc(summary)}</strong>
            </p>
            <p>A caller just spoke with{f' <strong>{_esc(agent_name)}</strong>' if agent_name else ' the assistant'}
               and is ready for follow-up.
               <strong>Next step:</strong> contact them on the phone number below.</p>
            <div class="details-box">
                <table style="width:100%; border-collapse:collapse;">
                    <tr><td style="padding:6px 12px 6px 0; vertical-align:top;"><strong>Name</strong></td>
                        <td>{name}</td></tr>
                    <tr><td style="padding:6px 12px 6px 0; vertical-align:top;"><strong>Phone</strong></td>
                        <td><a href="{_esc(phone_href)}">{phone}</a></td></tr>
                    <tr><td style="padding:6px 12px 6px 0; vertical-align:top;"><strong>Email</strong></td>
                        <td>{email}</td></tr>
                    <tr><td style="padding:6px 12px 6px 0; vertical-align:top;"><strong>Details</strong></td>
                        <td>{details_html}</td></tr>
                </table>
            </div>
            <p style="color:#666; font-size:12px; margin-bottom:0;">
                Workspace: {tenant_name}
                {f' &middot; Agent: {_esc(agent_name)}' if agent_name else ''}
                {f' &middot; Vertical: {_esc(service_type)}' if service_type else ''}
                <br>Captured at {captured_at} &middot; Call ID {call_id}
            </p>
        """
        return subject, EmailTemplates._create_html_wrapper(header_title, content, header_color="#1d4ed8")

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
