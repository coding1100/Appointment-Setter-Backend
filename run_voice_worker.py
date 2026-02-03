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

SIP HEADERS (set by Twilio webhook):
- X-LK-TenantId: tenant identifier
- X-LK-CallId: unique call identifier
- X-LK-CalledNumber: phone number that was called
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

# -------------------------------------------------
# CLI MODE DETECTION (OFFICIAL LIVEKIT PATTERN)
# -------------------------------------------------
IS_DOWNLOAD_ONLY = len(sys.argv) > 1 and sys.argv[1] == "download-files"

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

    # -------------------------------------------------
    # DOWNLOAD FILES MODE (NO CREDENTIALS REQUIRED)
    # -------------------------------------------------
    if IS_DOWNLOAD_ONLY:
        print("\n[DOWNLOAD FILES MODE]")
        print("=" * 70)
        print("Downloading LiveKit agent model files (VAD, Turn Detector, etc.)")
        print("No LiveKit credentials required.")
        print("=" * 70)

        try:
            # OFFICIAL LiveKit CLI entrypoint
            from livekit.agents.cli import main as cli_main

            # Emulate: python agent.py download-files
            sys.argv = ["livekit-agents", "download-files"]
            cli_main()

            print("\n✓ Model files downloaded successfully")
            sys.exit(0)

        except Exception as e:
            print(f"\n❌ Failed to download model files: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # -------------------------------------------------
    # WORKER MODE (CREDENTIALS REQUIRED)
    # -------------------------------------------------
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print(f"Agent Name: {AGENT_NAME}")
    print("  ↳ Single global agent handles ALL phone numbers")
    print("  ↳ Multi-tenant routing via SIP headers (X-LK-TenantId)")
    print("=" * 70)

    # Windows IPC warning suppressor
    if sys.platform == "win32":
        class WindowsIPCFilter(logging.Filter):
            def filter(self, record):
                msg = record.getMessage()
                return not ("DuplexClosed" in msg or "Error in _read_ipc_task" in msg)

        logging.getLogger("livekit.agents").addFilter(WindowsIPCFilter())

    try:
        import datetime
        from livekit import api as lk_api

        print("\n[PRE-FLIGHT CHECKS]")
        print("=" * 70)

        server_time = datetime.datetime.now(datetime.timezone.utc)
        print(f"Server UTC Time: {server_time.isoformat()}")
        print("  ⚠ JWT tokens are time-sensitive")

        print("\n[CREDENTIALS VERIFICATION]")
        print(f"  LIVEKIT_URL: {LIVEKIT_URL}")
        print(f"  LIVEKIT_API_KEY: {LIVEKIT_API_KEY[:10]}... (length: {len(LIVEKIT_API_KEY) if LIVEKIT_API_KEY else 0})")
        print(f"  LIVEKIT_API_SECRET: {'*' * 20}... (length: {len(LIVEKIT_API_SECRET) if LIVEKIT_API_SECRET else 0})")

        if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET or not LIVEKIT_URL:
            print("\n❌ ERROR: Missing LiveKit credentials!")
            sys.exit(1)

        # Validate token generation
        token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity("worker-test")
        token.with_grants(lk_api.VideoGrants(agent=True))
        jwt = token.to_jwt()

        if not jwt or len(jwt) < 20:
            print("\n❌ ERROR: Failed to generate JWT")
            sys.exit(1)

        print("✓ LiveKit credentials validated")

        # Ensure env vars are set explicitly
        os.environ["LIVEKIT_URL"] = LIVEKIT_URL
        os.environ["LIVEKIT_API_KEY"] = LIVEKIT_API_KEY
        os.environ["LIVEKIT_API_SECRET"] = LIVEKIT_API_SECRET

        print("\n[STARTING WORKER]")
        print("=" * 70)

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
        print("\n✓ Worker stopped by user")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN WORKER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
