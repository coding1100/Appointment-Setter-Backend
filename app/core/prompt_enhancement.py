"""
Pre-built instructions for voice-agent prompt enhancement via Gemini.

Production prompt structure and content are sourced from app.core.prompts.
"""

from __future__ import annotations

from app.core.prompts import get_template
from app.core.validators import validate_service_type

MAX_DRAFT_PROMPT_LENGTH = 4000
MAX_ENHANCED_PROMPT_LENGTH = 3899
AGENT_NAME_PLACEHOLDER = "[ Agent Name ]"
MAX_REFERENCE_LENGTH = 10000

PROMPT_ENHANCEMENT_INSTRUCTION = f"""You improve draft system prompts for MindRind real-time voice AI phone agents.

You will receive:
1. REFERENCE PRODUCTION PROMPT — the platform's gold-standard template for live voice agents.
2. DRAFT SYSTEM PROMPT — what the user wrote.

Rewrite the draft into a production-ready system prompt that:
- Preserves the user's business intent, domain focus, tone, and goals from the draft.
- Matches the structure, completeness, and operational standards shown in the reference (identity, voice style, fields to capture, step-by-step call flow, retry limits, off-topic handling, escalation, prompt-injection resistance, tool usage, and call closing where applicable).
- If the draft is support or reception focused rather than appointment booking, adapt the reference patterns to that purpose while keeping the same production quality.
- Never assign or invent a specific agent name. Wherever an agent name belongs, use exactly this placeholder: {AGENT_NAME_PLACEHOLDER}
- Do not replace {AGENT_NAME_PLACEHOLDER} with any real or fictional name from the draft or reference.
- Uses short, spoken-language instructions suitable for live phone calls.
- Uses plain text only — no markdown, bullets, numbering, section labels, or explanation of your edits.
- Output ONLY the final enhanced system prompt text (under 3900 characters)."""


def get_prompt_enhancement_instruction() -> str:
    return PROMPT_ENHANCEMENT_INSTRUCTION


def get_production_prompt_reference(service_type: str | None = None) -> str:
    """Load the production template from prompts.py for the given service type."""
    validated_service_type = validate_service_type(service_type) if service_type else "Home Services"
    reference = get_template(validated_service_type, AGENT_NAME_PLACEHOLDER)

    if len(reference) > MAX_REFERENCE_LENGTH:
        reference = (
            f"{reference[:MAX_REFERENCE_LENGTH].rstrip()}\n\n"
            "[Reference truncated — follow the same structure and standards throughout.]"
        )

    return reference


def build_enhancement_user_message(
    draft_prompt: str,
    *,
    service_type: str | None = None,
) -> str:
    reference = get_production_prompt_reference(service_type=service_type)

    return (
        "REFERENCE PRODUCTION PROMPT (structure and standards to follow):\n"
        f"{reference}\n\n"
        "---\n\n"
        "DRAFT SYSTEM PROMPT (rewrite this — keep the user's intent, align with the reference):\n"
        f"{draft_prompt.strip()}"
    )
