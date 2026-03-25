"""
Embed token generation and verification for chatbot launcher usage.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import CHATBOT_EMBED_SECRET, CHATBOT_EMBED_TOKEN_TTL_MINUTES, JWT_ALGORITHM


class ChatbotEmbedTokenService:
    """Service for issuing and validating chatbot embed tokens."""

    def create_token(self, chatbot_id: str, origin: str, version: int) -> Dict[str, str]:
        """Create short-lived embed token scoped to chatbot and origin."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=CHATBOT_EMBED_TOKEN_TTL_MINUTES)

        payload = {
            "sub": chatbot_id,
            "type": "chatbot_embed",
            "origin": origin,
            "ver": int(version),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, CHATBOT_EMBED_SECRET, algorithm=JWT_ALGORITHM)

        return {"token": token, "expires_at": expires_at.isoformat()}

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify token signature and claims."""
        try:
            payload = jwt.decode(token, CHATBOT_EMBED_SECRET, algorithms=[JWT_ALGORITHM])
        except ExpiredSignatureError as exc:
            raise ValueError("Embed token has expired") from exc
        except JWTError as exc:
            raise ValueError("Invalid embed token") from exc

        if payload.get("type") != "chatbot_embed":
            raise ValueError("Invalid embed token type")
        if not payload.get("sub"):
            raise ValueError("Invalid embed token subject")
        if not payload.get("origin"):
            raise ValueError("Invalid embed token origin")
        if "ver" not in payload:
            raise ValueError("Invalid embed token version")

        return payload


chatbot_embed_token_service = ChatbotEmbedTokenService()
