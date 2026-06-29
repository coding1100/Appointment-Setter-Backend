"""Unit tests for SMS App pure logic: template rendering, quiet-hours scheduling,
STOP/START keyword detection, the SMS-capable number filter, and Twilio-sourced
from-number resolution. These do not touch the database or Twilio."""

import asyncio
from datetime import datetime, timezone

import pytest

import app.api.v1.services.sms as sms_module
from app.api.v1.services.sms import (
    SmsCampaignService,
    SmsIntegrationService,
    SmsSendService,
    SmsWebhookService,
    render_template,
)


def test_render_template_fills_known_tokens():
    lead = {"name": "Alice", "phone_number": "+14155550123", "merge_fields": {"company": "Acme"}}
    body = "Hi {{name}} from {{company}} — reply to chat. ({{phone_number}})"
    assert render_template(body, lead) == "Hi Alice from Acme — reply to chat. (+14155550123)"


def test_render_template_unknown_token_is_blank():
    lead = {"name": "Bob", "merge_fields": {}}
    assert render_template("Hi {{name}}{{missing}}!", lead) == "Hi Bob!"


def test_render_template_handles_no_name():
    lead = {"merge_fields": {}}
    assert render_template("Hello {{name}}", lead) == "Hello "


def test_quiet_hours_defers_into_allowed_window():
    svc = SmsCampaignService()
    campaign = {"timezone": "UTC", "respect_quiet_hours": True}
    # 23:00 UTC falls inside the default quiet window (21 -> 9), should push to 09:00 next day.
    base = datetime(2026, 6, 29, 23, 0, tzinfo=timezone.utc)
    out = svc._next_send_time(base, delay_minutes=0, campaign=campaign)
    assert out.hour == 9
    assert out.date() > base.date()


def test_quiet_hours_allows_daytime_send():
    svc = SmsCampaignService()
    campaign = {"timezone": "UTC", "respect_quiet_hours": True}
    base = datetime(2026, 6, 29, 14, 0, tzinfo=timezone.utc)  # 2pm is allowed
    out = svc._next_send_time(base, delay_minutes=0, campaign=campaign)
    assert out == base


def test_quiet_hours_can_be_disabled():
    svc = SmsCampaignService()
    campaign = {"timezone": "UTC", "respect_quiet_hours": False}
    base = datetime(2026, 6, 29, 23, 30, tzinfo=timezone.utc)
    out = svc._next_send_time(base, delay_minutes=30, campaign=campaign)
    assert out.hour == 0  # 23:30 + 30m, no quiet-hours deferral


def test_stop_keyword_detection():
    svc = SmsWebhookService()
    assert svc._is_stop("STOP") is True
    assert svc._is_stop("  stop  ") is True
    assert svc._is_stop("UNSUBSCRIBE") is True
    assert svc._is_stop("hello there") is False


def test_start_keyword_detection():
    svc = SmsWebhookService()
    assert svc._is_start("START") is True
    assert svc._is_start("yes") is True
    assert svc._is_start("STOP") is False


# --- SMS-capable number filter + from-number resolution -----------------------


def _run(coro):
    return asyncio.run(coro)


def test_list_sms_capable_numbers_filters_non_sms(monkeypatch):
    """Only numbers with capabilities.sms == True are returned."""
    svc = SmsIntegrationService()

    async def fake_get_integration(tenant_id, decrypt=True):
        return {"account_sid": "AC1", "auth_token": "tok"}

    async def fake_get_available(account_sid, auth_token):
        return [
            {"phone_number": "+1111111111", "capabilities": {"voice": True, "sms": True}},
            {"phone_number": "+2222222222", "capabilities": {"voice": True, "sms": False}},
            {"phone_number": "+3333333333", "capabilities": {"sms": True, "mms": True}},
            {"phone_number": "+4444444444", "capabilities": {}},
        ]

    monkeypatch.setattr(svc, "get_integration", fake_get_integration)
    monkeypatch.setattr(
        sms_module.twilio_integration_service, "get_available_phone_numbers", fake_get_available
    )

    numbers = _run(svc.list_sms_capable_numbers("tenant-1"))
    got = {n["phone_number"] for n in numbers}
    assert got == {"+1111111111", "+3333333333"}


def test_resolve_from_number_defaults_to_first_capable(monkeypatch):
    send = SmsSendService()

    async def fake_capable(tenant_id):
        return [{"phone_number": "+1111111111"}, {"phone_number": "+3333333333"}]

    monkeypatch.setattr(sms_module.sms_integration_service, "list_sms_capable_numbers", fake_capable)
    assert _run(send.resolve_from_number("t1")) == "+1111111111"


def test_resolve_from_number_validates_preferred(monkeypatch):
    send = SmsSendService()

    async def fake_capable(tenant_id):
        return [{"phone_number": "+1111111111"}]

    monkeypatch.setattr(sms_module.sms_integration_service, "list_sms_capable_numbers", fake_capable)
    # A preferred number not on the SMS-capable list is rejected.
    with pytest.raises(ValueError):
        _run(send.resolve_from_number("t1", "+9999999999"))
    # A valid preferred number is accepted (normalized).
    assert _run(send.resolve_from_number("t1", "+1111111111")) == "+1111111111"
