"""
LiveKit Voice Agent Worker
==========================
Starts the voice agent worker that handles inbound telephony calls.

ARCHITECTURE (LiveKit Official Telephony Flow - Multi-Tenant Design):
- ONE worker with agent_name="voice-agent" handles ALL phone numbers
- Each phone number has its own dispatch rule pointing to "voice-agent"
- Worker receives jobs when LiveKit creates rooms via dispatch rule
- Worker extracts tenant_id, call_id, and called_number from SIP headers
- Worker loads config from Redis: tenant_config:<tenant_id>:<call_id>
- Worker FAILS if config is missing (no fallback to defaults)
"""

import os
import sys
import multiprocessing
import logging
from dotenv import load_dotenv

# -------------------------------------------------
# CRITICAL: Optimize ONNX / PyTorch threading
# -------------------------------------------------
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

# Load environment variables
load_dotenv()

from livekit import agents
from app.agents.voice_worker import entrypoint, prewarm_vad
from app.core.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

AGENT_NAME = "voice-agent"


if __name__ == "__main__":
    multiprocessing.freeze_support()

    print("=" * 70)
    print("Starting LiveKit Voice Agent Worker")
    print("=" * 70)
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print(f"Agent Name: {AGENT_NAME}")
    print(f"  ↳ Single global agent handles ALL phone numbers")
    print(f"  ↳ Multi-tenant routing via SIP headers (X-LK-TenantId)")
    print("=" * 70)

    # -------------------------------------------------
    # Windows IPC warning suppressor
    # -------------------------------------------------
    if sys.platform == "win32":
        class WindowsIPCFilter(logging.Filter):
            def filter(self, record):
                msg = record.getMessage()
                return not ("DuplexClosed" in msg or "Error in _read_ipc_task" in msg)

        logging.getLogger("livekit.agents").addFilter(WindowsIPCFilter())
        print("NOTE: Running on Windows — IPC watcher warnings suppressed.\n")

    try:
        # -------------------------------------------------
        # Ensure env vars are available for LiveKit SDK
        # -------------------------------------------------
        if LIVEKIT_URL:
            os.environ["LIVEKIT_URL"] = LIVEKIT_URL
        if LIVEKIT_API_KEY:
            os.environ["LIVEKIT_API_KEY"] = LIVEKIT_API_KEY
        if LIVEKIT_API_SECRET:
            os.environ["LIVEKIT_API_SECRET"] = LIVEKIT_API_SECRET

        print("[WORKER CONFIG]")
        print(f"  LIVEKIT_URL set: {'yes' if LIVEKIT_URL else 'no'}")
        print(f"  LIVEKIT_API_KEY set: {'yes' if LIVEKIT_API_KEY else 'no'}")
        print(f"  LIVEKIT_API_SECRET set: {'yes' if LIVEKIT_API_SECRET else 'no'}")
        print(f"  Agent Name: {AGENT_NAME}")
        print("=" * 70)

        # -------------------------------------------------
        # Start LiveKit worker
        # -------------------------------------------------
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
                prewarm_fnc=prewarm_vad,
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET,
                ws_url=LIVEKIT_URL,
                agent_name=AGENT_NAME,
                num_idle_processes=1,  # Prevent VAD contention
            )
        )

    except KeyboardInterrupt:
        print("\n✓ Worker stopped by user.")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN WORKER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
