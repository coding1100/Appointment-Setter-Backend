"""
Tests for voice worker email tool.
"""

import asyncio
import os
from datetime import datetime

import pytest

from app.agents.voice_worker import VoiceAgent
from app.core.config import email_settings


def test_send_appointment_confirmation_email_mocked(monkeypatch):
    calls = {}

    async def fake_send(
        self,
        customer_email,
        customer_name,
        appointment_datetime,
        service_type,
        service_address,
    ):
        calls["customer_email"] = customer_email
        calls["customer_name"] = customer_name
        calls["appointment_datetime"] = appointment_datetime
        calls["service_type"] = service_type
        calls["service_address"] = service_address
        return True

    def fake_init(self):
        return None

    monkeypatch.setattr("app.services.email.service.EmailService.__init__", fake_init)
    monkeypatch.setattr(
        "app.services.email.service.EmailService.send_appointment_confirmation",
        fake_send,
    )

    agent = VoiceAgent(instructions="test")
    result = asyncio.run(
        agent.send_appointment_confirmation_email(
            customer_email="test@example.com",
            customer_name="Test User",
            appointment_time="2025-01-01T10:00:00Z",
            service_type="Plumbing",
            service_address="123 Main St",
        )
    )

    assert result == "Appointment confirmation email sent successfully."
    assert calls["customer_email"] == "test@example.com"
    assert calls["customer_name"] == "Test User"
    assert isinstance(calls["appointment_datetime"], datetime)
    assert calls["appointment_datetime"].isoformat() == "2025-01-01T10:00:00+00:00"
    assert calls["service_type"] == "Plumbing"
    assert calls["service_address"] == "123 Main St"


@pytest.mark.integration
def test_send_appointment_confirmation_email_integration():
    if os.getenv("RUN_SMTP_TESTS") != "1":
        pytest.skip("Set RUN_SMTP_TESTS=1 to enable SMTP integration test")

    recipient = os.getenv("SMTP_TEST_RECIPIENT")
    if not recipient:
        pytest.skip("Set SMTP_TEST_RECIPIENT to enable SMTP integration test")

    if not (email_settings.MAIL_USERNAME and email_settings.MAIL_SERVER):
        pytest.skip("Email settings are not configured")

    agent = VoiceAgent(instructions="test")
    result = asyncio.run(
        agent.send_appointment_confirmation_email(
            customer_email=recipient,
            customer_name="SMTP Test",
            appointment_time="2025-01-01T10:00:00Z",
            service_type="Test Service",
            service_address="123 Test St",
        )
    )

    assert result == "Appointment confirmation email sent successfully."
