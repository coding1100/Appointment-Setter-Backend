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


def _voice_owner(voice_id: Optional[str]) -> Optional[str]:
    """Which provider owns this voice_id, per the central catalog.

    Returns None if the voice isn't in the catalog (legacy / typo / removed),
    in which case the caller falls back to the configured default ordering.
    """
    if not voice_id:
        return None
    voice = get_voice_by_id(voice_id)
    if not voice:
        return None
    owner = (voice.get("provider") or "").strip().lower()
    return owner or None


def _resolve_gemini_voice_name(voice_id: Optional[str]) -> str:
    """Pick the Gemini voice name to speak with.

    Priority:
      1. If `voice_id` is a Gemini voice in the catalog → use its name
         directly (this is the explicit user pick, e.g. "Zephyr").
      2. Otherwise (no pick, or pick belongs to another provider being used
         only as a Gemini fallback) → resolve by gender so the fallback
         voice at least matches the original voice's gender.
    """
    if _voice_owner(voice_id) == "gemini":
        return voice_id  # voice_id IS the Gemini voice name
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
    """Build the ElevenLabs TTS.

    Only forward `voice_id` to ElevenLabs when it actually belongs to
    ElevenLabs — sending it a Gemini voice name (e.g. "Zephyr") would 4xx.
    When ElevenLabs is used as the fallback for a Gemini-picked voice we
    just speak with its default voice.
    """
    if not ELEVEN_API_KEY:
        raise ValueError("ELEVEN_API_KEY is not configured")
    if voice_id and _voice_owner(voice_id) == "elevenlabs":
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
    Build the TTS pipeline.

    Provider routing rule (do not change without re-reading the docs):

      If the caller supplied an explicit `voice_id`, ElevenLabs MUST be the
      primary provider. Gemini TTS only accepts its own 30 named voices
      (Zephyr, Puck, Orus, Aoede, ...) per Google's official API and
      silently ignores any other identifier — so routing an ElevenLabs
      voice_id through Gemini collapses the entire voice picker into one
      generic male / one generic female voice. ElevenLabs is the only
      provider in this stack that can honor a specific picked voice.

      `FallbackAdapter` routes by provider FAILURE (per LiveKit's TTS docs),
      not by voice-ID compatibility, so ordering matters: the first entry
      is what the caller hears unless it errors. Gemini stays as a
      reliability fallback so a brief ElevenLabs outage doesn't kill calls.

      Only when no voice_id was picked do we honor
      `VOICE_TTS_PRIMARY_PROVIDER` — there's no specific voice to preserve,
      so the operator's preferred default provider wins.

    """
    owner = _voice_owner(voice_id)
    if owner == "elevenlabs":
        order = ["elevenlabs", "gemini"]
        logger.info("[TTS] voice_id=%s belongs to ElevenLabs — primary=ElevenLabs", voice_id)
    elif owner == "gemini":
        order = ["gemini", "elevenlabs"]
        logger.info("[TTS] voice_id=%s belongs to Gemini — primary=Gemini", voice_id)
    else:
        # No pick, or a legacy/unknown voice_id — honor the operator default.
        primary = VOICE_TTS_PRIMARY_PROVIDER.strip().lower()
        order = ["gemini", "elevenlabs"] if primary == "gemini" else ["elevenlabs", "gemini"]
        logger.info(
            "[TTS] voice_id=%s not in catalog — falling back to configured primary=%s",
            voice_id, primary,
        )

    providers: list[tts.TTS] = []
    for provider in order:
        try:
            if provider == "gemini":
                providers.append(_build_gemini_tts(voice_id))
            elif provider == "elevenlabs":
                providers.append(_build_elevenlabs_tts(voice_id, language_code))
        except Exception as exc:
            logger.warning("[TTS] Skipping %s provider: %s", provider, exc)

    if not providers:
        raise RuntimeError("No TTS providers available. Configure GOOGLE_API_KEY or ELEVEN_API_KEY.")

    if len(providers) == 1:
        return providers[0]

    return tts.FallbackAdapter(tts=providers, max_retry_per_tts=1)
