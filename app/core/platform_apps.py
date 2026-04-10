"""Platform app catalog and entitlement helpers."""

from typing import Any, Dict, Iterable, List, Optional

APPOINTMENT_SETTER_APP_ID = "appointment_setter"
CHATBOT_AGENTS_APP_ID = "chatbot_agents"

PLATFORM_APP_CATALOG: List[Dict[str, str]] = [
    {
        "id": APPOINTMENT_SETTER_APP_ID,
        "slug": "appointment-setter",
        "label": "Appointment Setter",
        "description": "Voice agents, tenant operations, appointments, telephony, and outbound calling.",
        "icon_key": APPOINTMENT_SETTER_APP_ID,
        "status": "active",
        "default_route": "/app/appointment-setter/dashboard",
    },
    {
        "id": CHATBOT_AGENTS_APP_ID,
        "slug": "chatbot-agents",
        "label": "Chatbot Agents",
        "description": "Chatbot launcher configuration, runtime logs, and embed controls.",
        "icon_key": CHATBOT_AGENTS_APP_ID,
        "status": "active",
        "default_route": "/app/chatbot-agents",
    },
]

ALL_PLATFORM_APP_IDS = [app["id"] for app in PLATFORM_APP_CATALOG]


def sanitize_app_ids(app_ids: Optional[Iterable[str]]) -> List[str]:
    if not app_ids:
        return []
    normalized: List[str] = []
    for app_id in app_ids:
        if not app_id:
            continue
        normalized_id = str(app_id).strip()
        if normalized_id in ALL_PLATFORM_APP_IDS and normalized_id not in normalized:
            normalized.append(normalized_id)
    return normalized


def get_platform_app_catalog() -> List[Dict[str, str]]:
    return [app.copy() for app in PLATFORM_APP_CATALOG]


def resolve_allowed_app_ids(user: Optional[Dict[str, Any]]) -> List[str]:
    if not user:
        return []
    explicit = sanitize_app_ids(user.get("allowed_app_ids"))
    if explicit:
        return explicit
    if str(user.get("role", "user")).lower() == "admin":
        return list(ALL_PLATFORM_APP_IDS)
    return [APPOINTMENT_SETTER_APP_ID]


def resolve_default_app_id(user: Optional[Dict[str, Any]]) -> Optional[str]:
    allowed_app_ids = resolve_allowed_app_ids(user)
    if not allowed_app_ids:
        return None
    requested_default = str((user or {}).get("default_app_id") or "").strip()
    if requested_default in allowed_app_ids:
        return requested_default
    return allowed_app_ids[0]


def has_app_access(user: Optional[Dict[str, Any]], app_id: str) -> bool:
    if not user:
        return False
    if str(user.get("role", "user")).lower() == "admin":
        return True
    return app_id in resolve_allowed_app_ids(user)
