"""
Environment variable validator to ensure all required configurations are set.
"""

import logging
import sys
from typing import List, Dict, Tuple

from app.core.config import (
    # Firebase
    FIREBASE_PROJECT_ID,
    FIREBASE_PRIVATE_KEY,
    FIREBASE_CLIENT_EMAIL,
    # Redis
    REDIS_URL,
    # LiveKit
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    # AI Services
    GOOGLE_API_KEY,
    DEEPGRAM_API_KEY,
    ELEVEN_API_KEY,
    # SendGrid
    SENDGRID_API_KEY,
    SENDGRID_FROM_EMAIL,
    # Application
    SECRET_KEY,
    ENVIRONMENT,
)

# Configure logging
logger = logging.getLogger(__name__)

# Define required and optional environment variables
REQUIRED_ENV_VARS = {
    # Critical for application functionality
    "SECRET_KEY": SECRET_KEY,
    "FIREBASE_PROJECT_ID": FIREBASE_PROJECT_ID,
    "FIREBASE_PRIVATE_KEY": FIREBASE_PRIVATE_KEY,
    "FIREBASE_CLIENT_EMAIL": FIREBASE_CLIENT_EMAIL,
    "REDIS_URL": REDIS_URL,
    "LIVEKIT_API_KEY": LIVEKIT_API_KEY,
    "LIVEKIT_API_SECRET": LIVEKIT_API_SECRET,
    "LIVEKIT_URL": LIVEKIT_URL,
}

OPTIONAL_ENV_VARS = {
    # Nice to have but not critical for basic operation
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "DEEPGRAM_API_KEY": DEEPGRAM_API_KEY,
    "ELEVEN_API_KEY": ELEVEN_API_KEY,
    "SENDGRID_API_KEY": SENDGRID_API_KEY,
    "SENDGRID_FROM_EMAIL": SENDGRID_FROM_EMAIL,
}


def validate_environment_variables(strict: bool = True) -> Tuple[bool, List[str]]:
    """
    Validate that all required environment variables are set.

    Args:
        strict: If True, fail on missing required vars. If False, just warn.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    warnings = []

    # Check required variables
    for var_name, var_value in REQUIRED_ENV_VARS.items():
        if not var_value or var_value.strip() == "":
            errors.append(f"Required environment variable '{var_name}' is not set or empty")

    # Check optional variables
    for var_name, var_value in OPTIONAL_ENV_VARS.items():
        if not var_value or var_value.strip() == "":
            warnings.append(f"Optional environment variable '{var_name}' is not set")

    # Log results
    if errors:
        logger.error("=" * 80)
        logger.error("ENVIRONMENT VARIABLE VALIDATION FAILED")
        logger.error("=" * 80)
        for error in errors:
            logger.error(f"❌ {error}")
        logger.error("=" * 80)
        logger.error("Please set the missing environment variables in your .env file")
        logger.error("=" * 80)

    if warnings:
        logger.warning("=" * 80)
        logger.warning("OPTIONAL ENVIRONMENT VARIABLES MISSING")
        logger.warning("=" * 80)
        for warning in warnings:
            logger.warning(f"⚠️  {warning}")
        logger.warning("=" * 80)
        logger.warning("Application will run with limited functionality")
        logger.warning("=" * 80)

    if not errors and not warnings:
        logger.info("=" * 80)
        logger.info("✅ All environment variables are properly configured")
        logger.info("=" * 80)

    is_valid = len(errors) == 0

    if not is_valid and strict:
        logger.critical("Application cannot start with missing required environment variables")
        logger.critical("Exiting...")
        sys.exit(1)

    return is_valid, errors + warnings


def get_environment_info() -> Dict[str, any]:
    """Get information about the current environment configuration."""
    return {
        "environment": ENVIRONMENT,
        "firebase_configured": bool(FIREBASE_PROJECT_ID and FIREBASE_PRIVATE_KEY and FIREBASE_CLIENT_EMAIL),
        "redis_configured": bool(REDIS_URL),
        "livekit_configured": bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET and LIVEKIT_URL),
        "google_ai_configured": bool(GOOGLE_API_KEY),
        "deepgram_configured": bool(DEEPGRAM_API_KEY),
        "elevenlabs_configured": bool(ELEVEN_API_KEY),
        "sendgrid_configured": bool(SENDGRID_API_KEY and SENDGRID_FROM_EMAIL),
        "secret_key_configured": bool(SECRET_KEY),
    }


def print_environment_summary():
    """Print a summary of environment configuration."""
    info = get_environment_info()

    logger.info("=" * 80)
    logger.info("ENVIRONMENT CONFIGURATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Environment: {info['environment']}")
    logger.info(f"Firebase: {'✅' if info['firebase_configured'] else '❌'}")
    logger.info(f"Redis: {'✅' if info['redis_configured'] else '❌'}")
    logger.info(f"LiveKit: {'✅' if info['livekit_configured'] else '❌'}")
    logger.info(f"Google AI (Gemini): {'✅' if info['google_ai_configured'] else '❌'}")
    logger.info(f"Deepgram (STT): {'✅' if info['deepgram_configured'] else '❌'}")
    logger.info(f"ElevenLabs (TTS): {'✅' if info['elevenlabs_configured'] else '❌'}")
    logger.info(f"SendGrid (Email): {'✅' if info['sendgrid_configured'] else '❌'}")
    logger.info(f"Secret Key: {'✅' if info['secret_key_configured'] else '❌'}")
    logger.info("=" * 80)
