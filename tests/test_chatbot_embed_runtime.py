"""
Tests for chatbot embed loader/panel runtime scripts.
"""

import pytest

from app.api.v1.routers import chatbot_embed as chatbot_embed_router


class _DummyClient:
    host = "127.0.0.1"


class _DummyRequest:
    client = _DummyClient()

    @staticmethod
    def url_for(name: str) -> str:
        assert name == "get_chatbot_embed_panel"
        return "https://api.example.com/api/v1/chatbot-embed/panel"


@pytest.mark.asyncio
async def test_chatbot_embed_panel_includes_voice_input_runtime():
    response = await chatbot_embed_router.get_chatbot_embed_panel(token="token-123")
    body = response.body.decode("utf-8")

    assert 'id="chatbot-mic"' in body
    assert "/api-static/vendor/annyang.min.js" in body
    assert "window.annyang.init({}, false);" in body
    assert "window.annyang.start" in body
    assert "initializeSpeechRecognition" in body


@pytest.mark.asyncio
async def test_chatbot_embed_loader_sets_microphone_iframe_permission(monkeypatch):
    async def _noop_rate_limit(*_args, **_kwargs):
        return None

    async def _fake_get_public_embed_config(token: str, request_origin: str):
        assert token == "token-abc"
        assert request_origin == "https://site.example.com"
        return {"chatbot_id": "cb-1"}

    async def _fake_get_chatbot_agent(chatbot_id: str):
        assert chatbot_id == "cb-1"
        return {
            "launcher_config": {
                "position": "bottom-right",
                "button_label": "Chat with us",
                "accent_color": "#0EA5E9",
            }
        }

    monkeypatch.setattr(chatbot_embed_router, "_enforce_public_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(chatbot_embed_router.chatbot_agent_service, "get_public_embed_config", _fake_get_public_embed_config)
    monkeypatch.setattr(chatbot_embed_router.chatbot_agent_service, "get_chatbot_agent", _fake_get_chatbot_agent)

    response = await chatbot_embed_router.get_chatbot_embed_loader(
        request=_DummyRequest(),
        token="token-abc",
        embed_origin=None,
        origin="https://site.example.com",
        referer=None,
    )
    script = response.body.decode("utf-8")

    assert 'iframe.allow = "microphone";' in script
