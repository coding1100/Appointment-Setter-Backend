"""
Centralized ElevenLabs voice metadata.
This module provides a single source of truth for all voice configurations.
"""

from typing import Dict, List, Optional

# Central list of all ElevenLabs voices with complete metadata
VOICE_METADATA: List[Dict[str, str]] = [
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel",
        "description": "Calm, natural, young adult female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "rachel.mp3",
    },
    {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi",
        "description": "Strong, confident, young adult female voice",
        "category": "female",
        "use_case": "conversational",
        "preview_filename": "domi.mp3",
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella",
        "description": "Soft, warm, young adult female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "bella.mp3",
    },
    {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni",
        "description": "Professional, well-rounded male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "antoni.mp3",
    },
    {
        "voice_id": "VR6AewLTigWG4xSOukaG",
        "name": "Arnold",
        "description": "Deep, authoritative male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "arnold.mp3",
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "description": "Deep, mature male voice",
        "category": "male",
        "use_case": "narration",
        "preview_filename": "adam.mp3",
    },
    {
        "voice_id": "yoZ06aMxZJJ28mfd3POQ",
        "name": "Sam",
        "description": "Young, dynamic male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "sam.mp3",
    },
    {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie",
        "description": "Casual, natural male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "charlie.mp3",
    },
    {
        "voice_id": "XB0fDUnXU5powFXDhCwa",
        "name": "Charlotte",
        "description": "Clear, professional female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "charlotte.mp3",
    },
    {
        "voice_id": "pqHfZKP75CvOlQylNhV4",
        "name": "Bill",
        "description": "Strong, trustworthy male voice",
        "category": "male",
        "use_case": "conversational",
        "preview_filename": "bill.mp3",
    },
    {
        "voice_id": "N2lVS1w4EtoT3dr4eOWO",
        "name": "Callum",
        "description": "Smooth, mature male voice",
        "category": "male",
        "use_case": "customer_service",
        "preview_filename": "callum.mp3",
    },
    {
        "voice_id": "LcfcDJNUP1GQjkzn1xUU",
        "name": "Emily",
        "description": "Warm, friendly female voice",
        "category": "female",
        "use_case": "customer_service",
        "preview_filename": "emily.mp3",
    },
]


def get_voice_by_id(voice_id: str) -> Optional[Dict[str, str]]:
    """
    Get voice metadata by voice_id.
    
    Args:
        voice_id: ElevenLabs voice ID
    
    Returns:
        Voice metadata dictionary or None if not found
    """
    for voice in VOICE_METADATA:
        if voice["voice_id"] == voice_id:
            return voice
    return None


def get_voice_preview_filename(voice_id: str) -> Optional[str]:
    """
    Get preview filename for a voice_id.
    
    Args:
        voice_id: ElevenLabs voice ID
    
    Returns:
        Preview filename (e.g., "rachel.mp3") or None if not found
    """
    voice = get_voice_by_id(voice_id)
    return voice["preview_filename"] if voice else None


def get_all_voices() -> List[Dict[str, str]]:
    """
    Get all voice metadata.
    
    Returns:
        List of all voice metadata dictionaries
    """
    return VOICE_METADATA.copy()

