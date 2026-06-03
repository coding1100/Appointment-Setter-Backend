"""
Centralized TTS voice metadata.

Single source of truth for every voice the platform can speak with, across all
supported providers. The active TTS provider (`VOICE_TTS_PRIMARY_PROVIDER`)
decides which subset of these voices is offered to operators in the UI.

Each entry carries a `provider` field — the TTS router in
`app.services.tts_provider` uses that field to decide which provider to send
the voice through (an ElevenLabs voice_id cannot be honored by Gemini, and a
Gemini voice name cannot be honored by ElevenLabs).

Provider conventions:
- ElevenLabs voices: `voice_id` is ElevenLabs's alphanumeric ID
  (e.g. "ErXwobaYiN019PkySvjV"). The same string is passed to
  `elevenlabs.TTS(voice_id=...)`.
- Gemini voices: `voice_id` is the prebuilt voice NAME from Google's API
  (e.g. "Zephyr", "Puck"). The same string is passed to
  `google.beta.GeminiTTS(voice_name=...)`. See
  https://ai.google.dev/gemini-api/docs/speech-generation for the catalog.
"""

from typing import Dict, List, Optional

# ElevenLabs canonical pre-made voices (stable, well-known IDs).
ELEVENLABS_VOICES: List[Dict[str, str]] = [
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel",
        "description": "Calm, natural, young adult female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "rachel.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi",
        "description": "Strong, confident, young adult female voice",
        "category": "female",
        "use_case": "conversational",
        "preview_filename": "domi.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella",
        "description": "Soft, warm, young adult female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "bella.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni",
        "description": "Professional, well-rounded male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "antoni.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "VR6AewLTigWG4xSOukaG",
        "name": "Arnold",
        "description": "Deep, authoritative male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "arnold.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "description": "Deep, mature male voice",
        "category": "male",
        "use_case": "narration",
        "preview_filename": "adam.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "yoZ06aMxZJJ28mfd3POQ",
        "name": "Sam",
        "description": "Young, dynamic male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "sam.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie",
        "description": "Casual, natural male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "charlie.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "XB0fDUnXU5powFXDhCwa",
        "name": "Charlotte",
        "description": "Clear, professional female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "charlotte.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "pqHfZKP75CvOlQylNhV4",
        "name": "Bill",
        "description": "Strong, trustworthy male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "bill.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "N2lVS1w4EtoT3dr4eOWO",
        "name": "Callum",
        "description": "Smooth, mature male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "callum.mp3",
        "provider": "elevenlabs",
    },
    {
        "voice_id": "LcfcDJNUP1GQjkzn1xUU",
        "name": "Emily",
        "description": "Warm, friendly female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "emily.mp3",
        "provider": "elevenlabs",
    },
]


# Gemini prebuilt voices — names from Google's official speech-generation API.
# https://ai.google.dev/gemini-api/docs/speech-generation
# No preview files are bundled; the preview endpoint will simply 404 for these
# until previews are recorded and added under app/static/voices.
def _gemini(name: str, category: str, description: str) -> Dict[str, str]:
    return {
        "voice_id": name,
        "name": name,
        "description": description,
        "category": category,
        "use_case": "general",
        "preview_filename": "",
        "provider": "gemini",
    }


GEMINI_VOICES: List[Dict[str, str]] = [
    _gemini("Zephyr", "female", "Bright"),
    _gemini("Puck", "male", "Upbeat"),
    _gemini("Charon", "male", "Informative"),
    _gemini("Kore", "female", "Firm"),
    _gemini("Fenrir", "male", "Excitable"),
    _gemini("Leda", "female", "Youthful"),
    _gemini("Orus", "male", "Firm"),
    _gemini("Aoede", "female", "Breezy"),
    _gemini("Callirrhoe", "female", "Easy-going"),
    _gemini("Autonoe", "female", "Bright"),
    _gemini("Enceladus", "male", "Breathy"),
    _gemini("Iapetus", "male", "Clear"),
    _gemini("Umbriel", "male", "Easy-going"),
    _gemini("Algieba", "male", "Smooth"),
    _gemini("Despina", "female", "Smooth"),
    _gemini("Erinome", "female", "Clear"),
    _gemini("Algenib", "male", "Gravelly"),
    _gemini("Rasalgethi", "male", "Informative"),
    _gemini("Laomedeia", "female", "Upbeat"),
    _gemini("Achernar", "female", "Soft"),
    _gemini("Alnilam", "male", "Firm"),
    _gemini("Schedar", "male", "Even"),
    _gemini("Gacrux", "female", "Mature"),
    _gemini("Pulcherrima", "female", "Forward"),
    _gemini("Achird", "male", "Friendly"),
    _gemini("Zubenelgenubi", "male", "Casual"),
    _gemini("Vindemiatrix", "female", "Gentle"),
    _gemini("Sadachbia", "male", "Lively"),
    _gemini("Sadaltager", "male", "Knowledgeable"),
    _gemini("Sulafat", "female", "Warm"),
]


# Aggregated, in stable order. Kept as a list (not a dict) so the UI can render
# the natural ordering chosen above.
VOICE_METADATA: List[Dict[str, str]] = [*ELEVENLABS_VOICES, *GEMINI_VOICES]


def get_voice_by_id(voice_id: str) -> Optional[Dict[str, str]]:
    """Look up a voice by its `voice_id` across every provider."""
    if not voice_id:
        return None
    for voice in VOICE_METADATA:
        if voice["voice_id"] == voice_id:
            return voice
    return None


def get_voice_preview_filename(voice_id: str) -> Optional[str]:
    """Return the bundled preview filename for a voice, if any (ElevenLabs only)."""
    voice = get_voice_by_id(voice_id)
    if not voice:
        return None
    filename = voice.get("preview_filename")
    return filename or None


def get_all_voices() -> List[Dict[str, str]]:
    """Return every voice in the catalog (both providers)."""
    return list(VOICE_METADATA)


def get_voices_by_provider(provider: Optional[str]) -> List[Dict[str, str]]:
    """Return only the voices owned by `provider` (e.g. 'elevenlabs', 'gemini').

    Returns the full catalog if `provider` is None/empty so a misconfigured
    deployment doesn't silently leave the UI empty.
    """
    if not provider:
        return list(VOICE_METADATA)
    normalized = provider.strip().lower()
    return [v for v in VOICE_METADATA if (v.get("provider") or "").lower() == normalized]
