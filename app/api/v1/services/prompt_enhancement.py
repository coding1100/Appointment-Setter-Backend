"""
Prompt enhancement service for voice agent configuration.
"""

from __future__ import annotations

from typing import Optional

from app.core.prompt_enhancement import (
    MAX_DRAFT_PROMPT_LENGTH,
    MAX_ENHANCED_PROMPT_LENGTH,
    build_enhancement_user_message,
    get_prompt_enhancement_instruction,
)
from app.services.gemini_text import generate_text


class PromptEnhancementService:
    def get_enhancement_instruction(self) -> str:
        return get_prompt_enhancement_instruction()

    async def enhance_prompt(
        self,
        draft_prompt: str,
        *,
        service_type: Optional[str] = None,
    ) -> str:
        draft = draft_prompt.strip()
        if not draft:
            raise ValueError("Prompt cannot be empty.")
        if len(draft) > MAX_DRAFT_PROMPT_LENGTH:
            raise ValueError(f"Prompt must be at most {MAX_DRAFT_PROMPT_LENGTH} characters.")

        enhanced = await generate_text(
            system_instruction=get_prompt_enhancement_instruction(),
            user_message=build_enhancement_user_message(
                draft,
                service_type=service_type,
            ),
            temperature=0.4,
            max_output_tokens=4096,
        )

        if not enhanced:
            raise ValueError("Gemini returned an empty enhanced prompt.")

        return enhanced[:MAX_ENHANCED_PROMPT_LENGTH]


prompt_enhancement_service = PromptEnhancementService()
