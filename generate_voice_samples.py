"""
Voice Sample Generator Script
==============================
This script generates audio samples for all ElevenLabs voices used in the agent system.
Run this script ONCE to create all voice preview files.

Usage:
    python generate_voice_samples.py

Requirements:
    - ELEVEN_API_KEY must be set in .env file
    - elevenlabs package must be installed (pip install elevenlabs)
    - Internet connection for API calls

Output:
    Creates 12 MP3 files in app/static/voices/ directory
"""

import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

if not ELEVEN_API_KEY:
    print("❌ ERROR: ELEVEN_API_KEY not found in .env file")
    print("Please add your ElevenLabs API key to .env file:")
    print('ELEVEN_API_KEY=sk_your_api_key_here')
    sys.exit(1)

# Create voices directory if it doesn't exist
VOICES_DIR = Path("app/static/voices")
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Sample text to generate for all voices
SAMPLE_TEXT = "Hello! This is a preview of my voice. I'm here to help you schedule appointments and answer your questions. Thank you for calling!"

# List of all voices to generate (matching backend voice list)
VOICES = [
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel",
        "filename": "rachel.mp3"
    },
    {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi",
        "filename": "domi.mp3"
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella",
        "filename": "bella.mp3"
    },
    {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni",
        "filename": "antoni.mp3"
    },
    {
        "voice_id": "VR6AewLTigWG4xSOukaG",
        "name": "Arnold",
        "filename": "arnold.mp3"
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "filename": "adam.mp3"
    },
    {
        "voice_id": "yoZ06aMxZJJ28mfd3POQ",
        "name": "Sam",
        "filename": "sam.mp3"
    },
    {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie",
        "filename": "charlie.mp3"
    },
    {
        "voice_id": "XB0fDUnXU5powFXDhCwa",
        "name": "Charlotte",
        "filename": "charlotte.mp3"
    },
    {
        "voice_id": "pqHfZKP75CvOlQylNhV4",
        "name": "Bill",
        "filename": "bill.mp3"
    },
    {
        "voice_id": "N2lVS1w4EtoT3dr4eOWO",
        "name": "Callum",
        "filename": "callum.mp3"
    },
    {
        "voice_id": "LcfcDJNUP1GQjkzn1xUU",
        "name": "Emily",
        "filename": "emily.mp3"
    }
]


def generate_voice_sample(voice_id: str, voice_name: str, filename: str) -> bool:
    """
    Generate audio sample for a single voice using ElevenLabs API.
    
    Args:
        voice_id: ElevenLabs voice ID
        voice_name: Human-readable voice name
        filename: Output filename (e.g., "rachel.mp3")
    
    Returns:
        True if successful, False otherwise
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_API_KEY
    }
    
    data = {
        "text": SAMPLE_TEXT,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    try:
        print(f"🎤 Generating audio for {voice_name}...", end=" ", flush=True)
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # Save audio file
            output_path = VOICES_DIR / filename
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content) / 1024  # KB
            print(f"✅ Success! ({file_size:.1f} KB)")
            return True
        else:
            print(f"❌ Failed! Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Failed! Request timed out")
        return False
    except Exception as e:
        print(f"❌ Failed! Error: {str(e)}")
        return False


def main():
    """Main function to generate all voice samples."""
    print("=" * 60)
    print("🎵 Voice Sample Generator for Agent Management System")
    print("=" * 60)
    print(f"\n📁 Output directory: {VOICES_DIR.absolute()}")
    print(f"📝 Sample text: {SAMPLE_TEXT[:50]}...")
    print(f"🎯 Total voices to generate: {len(VOICES)}\n")
    
    # Check if API key is valid format
    if not ELEVEN_API_KEY.startswith("sk_"):
        print("⚠️  WARNING: API key doesn't start with 'sk_' - it might be invalid")
        print()
    
    # Generate all voice samples
    successful = 0
    failed = 0
    
    for i, voice in enumerate(VOICES, 1):
        print(f"[{i}/{len(VOICES)}] ", end="")
        
        if generate_voice_sample(voice["voice_id"], voice["name"], voice["filename"]):
            successful += 1
        else:
            failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Generation Summary")
    print("=" * 60)
    print(f"✅ Successful: {successful}/{len(VOICES)}")
    print(f"❌ Failed: {failed}/{len(VOICES)}")
    
    if failed > 0:
        print("\n⚠️  Some voices failed to generate. Possible reasons:")
        print("   - Invalid API key")
        print("   - Insufficient credits")
        print("   - Network issues")
        print("   - Rate limit exceeded")
        print("\nPlease check your ElevenLabs account and try again.")
    else:
        print(f"\n🎉 All voice samples generated successfully!")
        print(f"📂 Files saved to: {VOICES_DIR.absolute()}")
        print("\n✨ Your agent management system is now ready with voice previews!")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

