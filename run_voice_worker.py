"""
Run the LiveKit Voice Agent Worker
This script starts the LiveKit agent worker that handles voice interactions.
"""
import os
import multiprocessing
from dotenv import load_dotenv

# Load environment variables BEFORE importing from app.core.config
load_dotenv()

from app.agents.voice_worker import entrypoint
from livekit import agents
from app.core.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    print("="  * 60)
    print("Starting LiveKit Voice Agent Worker...")
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print("=" * 60)
    
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
            ws_url=LIVEKIT_URL,
        )
    )

