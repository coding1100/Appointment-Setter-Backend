"""
Tests for environment validation.
"""

import pytest

from app.core.env_validator import get_environment_info, validate_environment_variables


def test_get_environment_info():
    """Test getting environment configuration information."""
    info = get_environment_info()

    # Check that the structure is correct (returns configuration status dict)
    assert isinstance(info, dict)
    assert "environment" in info
    assert "firebase_configured" in info
    assert "redis_configured" in info
    assert "livekit_configured" in info
    assert "google_ai_configured" in info
    assert "deepgram_configured" in info
    assert "elevenlabs_configured" in info
    assert "sendgrid_configured" in info
    assert "secret_key_configured" in info

    # Check that boolean values are returned
    for key in ["firebase_configured", "redis_configured", "livekit_configured", 
                "google_ai_configured", "deepgram_configured", "elevenlabs_configured",
                "sendgrid_configured", "secret_key_configured"]:
        assert isinstance(info[key], bool)


def test_validate_environment_variables():
    """Test environment variable validation (non-strict mode)."""
    # Test that it returns a tuple of (bool, list)
    is_valid, errors = validate_environment_variables(strict=False)
    assert isinstance(is_valid, bool)
    assert isinstance(errors, list)
    # In test mode, validation should pass (skip validation)
    assert is_valid is True
