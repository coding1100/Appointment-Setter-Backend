"""
Tests for chatbot embed token service.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.chatbot_agents.token_service import ChatbotEmbedTokenService
from app.core.config import CHATBOT_EMBED_SECRET, JWT_ALGORITHM


def test_create_and_verify_embed_token_roundtrip():
    """Token should decode with expected claims."""
    service = ChatbotEmbedTokenService()

    token_data = service.create_token(chatbot_id="chatbot-123", origin="https://app.example.com", version=3)
    claims = service.verify_token(token_data["token"])

    assert claims["sub"] == "chatbot-123"
    assert claims["type"] == "chatbot_embed"
    assert claims["origin"] == "https://app.example.com"
    assert claims["ver"] == 3


def test_verify_embed_token_expired():
    """Expired token should be rejected."""
    service = ChatbotEmbedTokenService()
    expired = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
    payload = {
        "sub": "chatbot-123",
        "type": "chatbot_embed",
        "origin": "https://app.example.com",
        "ver": 1,
        "iat": expired - 60,
        "exp": expired,
    }
    token = jwt.encode(payload, CHATBOT_EMBED_SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(ValueError, match="expired"):
        service.verify_token(token)
