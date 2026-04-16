"""
Platform app catalog and access helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

PLATFORM_APPS: List[Dict[str, str]] = [
    {
        "id": "appointment_setter",
        "slug": "appointment-setter",
        "label": "Appointment Setter",
        "default_route": "/app/appointment-setter/dashboard",
        "icon_key": "appointment_setter",
        "description": "Calling and scheduling",
    },
    {
        "id": "chatbot_agents",
        "slug": "chatbot-agents",
        "label": "Chatbot Agents",
        "default_route": "/app/chatbot-agents",
        "icon_key": "chatbot_agents",
        "description": "Launchers and embeds",
    },
    {
        "id": "users",
        "slug": "users",
        "label": "Users",
        "default_route": "/app/users",
        "icon_key": "users",
        "description": "Staff, roles, and access",
    },
]

_PLATFORM_APP_IDS: Set[str] = {app["id"] for app in PLATFORM_APPS}


def get_platform_apps() -> List[Dict[str, str]]:
    """Return platform app catalog."""
    return [dict(app) for app in PLATFORM_APPS]


def get_platform_app_ids() -> List[str]:
    """Return valid app IDs."""
    return [app["id"] for app in PLATFORM_APPS]


def normalize_allowed_app_ids(app_ids: Optional[Sequence[str]]) -> List[str]:
    """Filter and deduplicate incoming app IDs while preserving order."""
    if not app_ids:
        return []

    normalized: List[str] = []
    seen: Set[str] = set()
    for app_id in app_ids:
        if not isinstance(app_id, str):
            continue
        cleaned = app_id.strip()
        if not cleaned or cleaned in seen or cleaned not in _PLATFORM_APP_IDS:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def get_default_allowed_app_ids_for_role(role: str) -> List[str]:
    """Default app set for a role when explicit app access is missing."""
    role_name = (role or "").strip().lower()

    if role_name == "admin":
        return get_platform_app_ids()
    if role_name in {"tenant_admin", "tenant_user", "user"}:
        return ["appointment_setter"]

    return ["appointment_setter"]


def resolve_user_allowed_app_ids(user: Dict[str, Any]) -> List[str]:
    """
    Resolve effective app access for a user.

    Priority:
    1) explicit user.allowed_app_ids
    2) role defaults
    """
    role = str(user.get("role") or "").lower()
    explicit = normalize_allowed_app_ids(user.get("allowed_app_ids"))
    if explicit:
        return explicit
    return get_default_allowed_app_ids_for_role(role)


def resolve_user_default_app_id(user: Dict[str, Any], allowed_app_ids: Sequence[str]) -> str:
    """Resolve the user's default app from profile and allowed list."""
    preferred = user.get("default_app_id")
    if isinstance(preferred, str) and preferred in allowed_app_ids:
        return preferred

    if allowed_app_ids:
        return allowed_app_ids[0]

    return "appointment_setter"


def has_app_access(user: Dict[str, Any], app_id: str) -> bool:
    """Check app access for user."""
    if str(user.get("role") or "").lower() == "admin":
        return app_id in _PLATFORM_APP_IDS
    return app_id in resolve_user_allowed_app_ids(user)
