"""
Tests for prompt enhancement service.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.services.prompt_enhancement import PromptEnhancementService
from app.core.prompt_enhancement import build_enhancement_user_message, get_production_prompt_reference


@pytest.mark.asyncio
async def test_enhance_prompt_returns_trimmed_result():
    service = PromptEnhancementService()
    with patch(
        "app.api.v1.services.prompt_enhancement.generate_text",
        new=AsyncMock(return_value="  Enhanced voice-agent prompt.  "),
    ):
        result = await service.enhance_prompt(
            "You are a helpful receptionist.",
            service_type="Home Services",
        )

    assert result == "Enhanced voice-agent prompt."


@pytest.mark.asyncio
async def test_enhance_prompt_rejects_empty_draft():
    service = PromptEnhancementService()
    with pytest.raises(ValueError, match="cannot be empty"):
        await service.enhance_prompt("   ")


@pytest.mark.asyncio
async def test_enhance_prompt_truncates_to_max_length():
    service = PromptEnhancementService()
    with patch(
        "app.api.v1.services.prompt_enhancement.generate_text",
        new=AsyncMock(return_value="y" * 5000),
    ):
        result = await service.enhance_prompt("x" * 100, service_type="Home Services")

    assert len(result) == 3899


def test_build_enhancement_user_message_includes_production_reference():
    message = build_enhancement_user_message(
        "You are a customer support agent.",
        service_type="Home Services",
    )

    reference = get_production_prompt_reference(service_type="Home Services")
    assert "REFERENCE PRODUCTION PROMPT" in message
    assert reference in message
    assert "DRAFT SYSTEM PROMPT" in message
    assert "You are a customer support agent." in message
