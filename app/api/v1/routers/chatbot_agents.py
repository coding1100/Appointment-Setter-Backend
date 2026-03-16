"""
Chatbot agent management APIs (non-tenant).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.routers.auth import get_current_user_from_token
from app.api.v1.schemas.chatbot_agent import (
    ChatbotAgentCreate,
    ChatbotAgentResponse,
    ChatbotAgentUpdate,
    ChatbotEmbedRevokeResponse,
    ChatbotEmbedTokenRequest,
    ChatbotEmbedTokenResponse,
    ChatbotRuntimeControlRequest,
    ChatbotRuntimeControlResponse,
    ChatbotRuntimeLogResponse,
)
from app.chatbot_agents.service import chatbot_agent_service

router = APIRouter(prefix="/chatbot-agents", tags=["chatbot-agents"])
_CHATBOT_V2_REQUIRED_FIELDS = (
    "domain_key",
    "behavior_config",
    "knowledge_config",
    "launcher_config",
    "embed_token_version",
)


def _is_admin(current_user: Dict[str, Any]) -> bool:
    return str(current_user.get("role", "")).lower() == "admin"


def _require_v2_chatbot_schema(chatbot: Dict[str, Any]) -> None:
    """Reject legacy chatbot documents that were not migrated to v2 schema."""
    missing_fields = [field for field in _CHATBOT_V2_REQUIRED_FIELDS if field not in chatbot]
    if not missing_fields:
        return

    chatbot_id = chatbot.get("id", "unknown")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Chatbot agent '{chatbot_id}' uses a legacy schema and is missing required fields: "
            f"{', '.join(missing_fields)}. Run migration script: python scripts/migrate_chatbot_agents_v2.py"
        ),
    )


def _to_chatbot_response(chatbot: Dict[str, Any]) -> ChatbotAgentResponse:
    """Map persisted chatbot dict to response schema."""
    _require_v2_chatbot_schema(chatbot)
    return ChatbotAgentResponse(
        id=chatbot["id"],
        agent_type="chatbot",
        owner_user_id=chatbot["owner_user_id"],
        name=chatbot["name"],
        welcome_message=chatbot["welcome_message"],
        allowed_origins=chatbot["allowed_origins"],
        theme=chatbot["theme"],
        status=chatbot["status"],
        domain_key=chatbot["domain_key"],
        custom_domain_name=chatbot.get("custom_domain_name"),
        behavior_config=chatbot["behavior_config"],
        knowledge_config=chatbot["knowledge_config"],
        launcher_config=chatbot["launcher_config"],
        embed_token_version=int(chatbot["embed_token_version"]),
        created_at=chatbot["created_at"],
        updated_at=chatbot["updated_at"],
    )


@router.post("", response_model=ChatbotAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_chatbot_agent(
    chatbot_data: ChatbotAgentCreate, current_user: Dict[str, Any] = Depends(get_current_user_from_token)
):
    owner_user_id = str(current_user.get("id", ""))
    created = await chatbot_agent_service.create_chatbot_agent(owner_user_id=owner_user_id, payload=chatbot_data.dict())
    return _to_chatbot_response(created)


@router.get("", response_model=List[ChatbotAgentResponse])
async def list_chatbot_agents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user_from_token),
):
    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    chatbots = await chatbot_agent_service.list_chatbot_agents_for_user(user_id, role, limit=limit, offset=offset)
    return [_to_chatbot_response(chatbot) for chatbot in chatbots]


@router.get("/{chatbot_id}", response_model=ChatbotAgentResponse)
async def get_chatbot_agent(chatbot_id: str, current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _to_chatbot_response(chatbot)


@router.put("/{chatbot_id}", response_model=ChatbotAgentResponse)
async def update_chatbot_agent(
    chatbot_id: str, chatbot_data: ChatbotAgentUpdate, current_user: Dict[str, Any] = Depends(get_current_user_from_token)
):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        updated = await chatbot_agent_service.update_chatbot_agent(chatbot_id, chatbot_data.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    return _to_chatbot_response(updated)


@router.delete("/{chatbot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chatbot_agent(chatbot_id: str, current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    success = await chatbot_agent_service.delete_chatbot_agent(chatbot_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")
    return None


@router.post("/{chatbot_id}/embed-token", response_model=ChatbotEmbedTokenResponse)
async def generate_chatbot_embed_token(
    chatbot_id: str, payload: ChatbotEmbedTokenRequest, current_user: Dict[str, Any] = Depends(get_current_user_from_token)
):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        token_data = await chatbot_agent_service.create_embed_token(chatbot, payload.origin)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChatbotEmbedTokenResponse(**token_data)


@router.post("/{chatbot_id}/revoke-embed-tokens", response_model=ChatbotEmbedRevokeResponse)
async def revoke_embed_tokens(chatbot_id: str, current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        updated = await chatbot_agent_service.revoke_embed_tokens(chatbot_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ChatbotEmbedRevokeResponse(
        chatbot_id=chatbot_id,
        embed_token_version=int(updated["embed_token_version"]),
        revoked_at=datetime.now(timezone.utc),
    )


@router.get("/{chatbot_id}/runtime-logs", response_model=List[ChatbotRuntimeLogResponse])
async def list_runtime_logs(
    chatbot_id: str,
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user_from_token),
):
    chatbot = await chatbot_agent_service.get_chatbot_agent(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot agent not found")

    user_id = str(current_user.get("id", ""))
    role = str(current_user.get("role", "user")).lower()
    if not chatbot_agent_service.can_manage(chatbot, user_id=user_id, role=role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    logs = await chatbot_agent_service.get_runtime_logs(chatbot_id=chatbot_id, limit=limit, status_filter=status_filter)
    return [
        ChatbotRuntimeLogResponse(
            request_id=log["request_id"],
            chatbot_id=log["chatbot_id"],
            status=log["status"],
            latency_ms=int(log.get("latency_ms", 0)),
            error_code=log.get("error_code"),
            timestamp=datetime.fromisoformat(log["timestamp"]),
        )
        for log in logs
    ]


@router.get("/runtime/kill-switch", response_model=ChatbotRuntimeControlResponse)
async def get_runtime_kill_switch(current_user: Dict[str, Any] = Depends(get_current_user_from_token)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    enabled = await chatbot_agent_service.get_runtime_enabled()
    return ChatbotRuntimeControlResponse(
        enabled=enabled,
        updated_at=datetime.now(timezone.utc),
        updated_by=str(current_user.get("id", "")),
    )


@router.post("/runtime/kill-switch", response_model=ChatbotRuntimeControlResponse)
async def set_runtime_kill_switch(
    payload: ChatbotRuntimeControlRequest, current_user: Dict[str, Any] = Depends(get_current_user_from_token)
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    updated = await chatbot_agent_service.set_runtime_enabled(enabled=payload.enabled, updated_by=str(current_user.get("id")))
    return ChatbotRuntimeControlResponse(
        enabled=bool(updated.get("enabled", payload.enabled)),
        updated_at=datetime.fromisoformat(updated.get("updated_at", datetime.now(timezone.utc).isoformat())),
        updated_by=str(updated.get("updated_by", current_user.get("id"))),
    )
