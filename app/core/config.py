"""
Core configuration settings for the AI Phone Scheduler SaaS platform.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Firebase settings (Minimal Required Fields)
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "")
FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL", "")

# Redis settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# LiveKit settings
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
# LiveKit SIP domain for Twilio integration (separate from WebSocket URL)
# Configure SIP Inbound Trunk in LiveKit Cloud and use that domain here
# Example: 3nbu801ppzl.sip.livekit.cloud (NOT the WebSocket domain)
# Get this from LiveKit Cloud Dashboard → SIP → Inbound Trunks
LIVEKIT_SIP_DOMAIN = os.environ.get("LIVEKIT_SIP_DOMAIN", "")

# Twilio settings
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WEBHOOK_BASE_URL = os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")

# AI Services settings
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# SendGrid settings
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "")

# AWS settings
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Application settings
DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "t")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
API_HOST = os.environ.get("API_HOST", "0.0.0.0")  # nosec B104 - Intentional: Server needs to bind to all interfaces
API_PORT = int(os.environ.get("API_PORT", "8000"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

# JWT settings
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Security settings
SECRET_KEY = os.environ.get("SECRET_KEY", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# Home Services voice mapping
VOICE_MAP: Dict[str, str] = {
    "Home Services": "en_us_006",
    "Plumbing": "en_us_006",
    "Electrician": "en_us_006",
    "Painter": "en_us_006",
    "Carpenter": "en_us_006",
    "Maids": "en_us_006",
}

# Home Services prompt mapping
PROMPT_MAP: Dict[str, str] = {
    "Home Services": "custom_prompt_home_services",
    "Plumbing": "custom_prompt_plumbing",
    "Electrician": "custom_prompt_electrician",
    "Painter": "custom_prompt_painter",
    "Carpenter": "custom_prompt_carpenter",
    "Maids": "custom_prompt_maids",
}
