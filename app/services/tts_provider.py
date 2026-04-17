"""
TTS provider orchestration for voice agents.

Primary: Gemini TTS
Fallback: ElevenLabs
"""

import logging
from typing import Optional

from livekit.agents import tts
from livekit.plugins import elevenlabs, google

from app.core.config import (
    ELEVEN_API_KEY,
    ELEVEN_TTS_MODEL,
    GEMINI_TTS_MODEL,
    GEMINI_TTS_VOICE_FEMALE,
    GEMINI_TTS_VOICE_MALE,
    GOOGLE_API_KEY,
    VOICE_TTS_PRIMARY_PROVIDER,
)
from app.core.voice_metadata import get_voice_by_id

logger = logging.getLogger(__name__)

DEFAULT_GENDER = "female"


def _resolve_gender_from_voice_id(voice_id: Optional[str]) -> str:
    if not voice_id:
        return DEFAULT_GENDER
    voice = get_voice_by_id(voice_id)
    if not voice:
        return DEFAULT_GENDER
    category = (voice.get("category") or "").strip().lower()
    if category in {"male", "female"}:
        return category
    return DEFAULT_GENDER


def _resolve_gemini_voice_name(voice_id: Optional[str]) -> str:
    gender = _resolve_gender_from_voice_id(voice_id)
    return GEMINI_TTS_VOICE_MALE if gender == "male" else GEMINI_TTS_VOICE_FEMALE


def _build_gemini_tts(voice_id: Optional[str]) -> tts.TTS:
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not configured")
    voice_name = _resolve_gemini_voice_name(voice_id)
    return google.beta.GeminiTTS(
        model=GEMINI_TTS_MODEL,
        voice_name=voice_name,
        api_key=GOOGLE_API_KEY,
    )


def _build_elevenlabs_tts(voice_id: Optional[str], language_code: str) -> tts.TTS:
    if not ELEVEN_API_KEY:
        raise ValueError("ELEVEN_API_KEY is not configured")
    if voice_id:
        return elevenlabs.TTS(
            api_key=ELEVEN_API_KEY,
            voice_id=voice_id,
            model=ELEVEN_TTS_MODEL,
            language=language_code,
            enable_ssml_parsing=False,
        )
    return elevenlabs.TTS(api_key=ELEVEN_API_KEY)


def build_tts_with_fallback(voice_id: Optional[str], language_code: str = "en") -> tts.TTS:
    """
    Build TTS pipeline with provider-level fallback.

    Gemini is primary by default; ElevenLabs is fallback.
    """
    providers: list[tts.TTS] = []

    primary = VOICE_TTS_PRIMARY_PROVIDER.strip().lower()
    order = ["gemini", "elevenlabs"] if primary == "gemini" else ["elevenlabs", "gemini"]

    for provider in order:
        try:
            if provider == "gemini":
                providers.append(_build_gemini_tts(voice_id))
            elif provider == "elevenlabs":
                providers.append(_build_elevenlabs_tts(voice_id, language_code))
        except Exception as exc:
            logger.warning("Skipping %s TTS provider: %s", provider, exc)

    if not providers:
        raise RuntimeError("No TTS providers available. Configure GOOGLE_API_KEY or ELEVEN_API_KEY.")

    if len(providers) == 1:
        return providers[0]

    return tts.FallbackAdapter(tts=providers, max_retry_per_tts=1)
