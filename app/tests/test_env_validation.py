"""
Tests for environment validation.
"""
import pytest
from app.core.env_validator import get_environment_info, validate_environment_variables


def test_get_environment_info():
    """Test getting environment configuration information."""
    info = get_environment_info()
    
    # Check that the structure is correct
    assert "required" in info
    assert "optional" in info
    assert isinstance(info["required"], list)
    assert isinstance(info["optional"], list)
    
    # Check that each item has expected fields
    for var_data in info["required"]:
        assert "name" in var_data
        assert "description" in var_data
        assert "is_set" in var_data
        assert "value_present" in var_data
        assert isinstance(var_data["is_set"], bool)
        assert isinstance(var_data["value_present"], bool)
    
    for var_data in info["optional"]:
        assert "name" in var_data
        assert "description" in var_data
        assert "is_set" in var_data
        assert "value_present" in var_data
        assert isinstance(var_data["is_set"], bool)
        assert isinstance(var_data["value_present"], bool)


def test_validate_environment_variables():
    """Test environment variable validation (non-strict mode)."""
    # Test that it returns a boolean
    result = validate_environment_variables(strict=False)
    assert isinstance(result, bool)

