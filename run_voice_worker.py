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
- X-LK-TenantId: tenant identifier for multi-tenant routing
- X-LK-CallId: unique call identifier for config lookup
- X-LK-CalledNumber: the phone number that was called

DISPATCH RULE CONFIGURATION (auto-created by backend per phone number):
{
  "name": "dispatch-rule-{phone_number}",
  "rule": {
    "dispatchRuleIndividual": {
      "roomPrefix": "call-"
    }
  },
  "roomConfig": {
    "agents": [
      { "agentName": "voice-agent" }  // Same for ALL phone numbers
    ]
  },
  "trunkIds": [trunk_id]
}

MULTI-TENANT ROUTING:
- Worker identifies tenant via SIP header X-LK-TenantId (not agent name)
- Worker identifies phone number via SIP header X-LK-CalledNumber
- One worker = unlimited phone numbers = unlimited tenants
"""

import os
import sys
import multiprocessing
import logging
from dotenv import load_dotenv

# CRITICAL: Optimize ONNX/PyTorch threading BEFORE importing any ML libraries
# Without this, multiple threads compete for CPU and cause 20-30 second VAD delays
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

# Load environment variables before importing config
load_dotenv()

from livekit import agents
from app.agents.voice_worker import entrypoint, prewarm_vad
from app.core.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL


# Single global agent name - one worker handles ALL phone numbers
# Multi-tenant routing is done via SIP headers, not agent names
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
    print("")
    print("ARCHITECTURE (Multi-Tenant Design):")
    print("  1. Twilio → Backend → stores tenant_config:<tenant_id>:<call_id>")
    print("  2. Backend → TwiML <Dial><Sip> with SIP headers")
    print("  3. Backend auto-creates dispatch rule per phone number")
    print("  4. ALL dispatch rules use agentName='voice-agent'")
    print("  5. LiveKit dispatch rule creates room: call-{phone}_{suffix}")
    print("  6. Worker extracts tenant_id + call_id from SIP headers")
    print("  7. Worker loads config from Redis")
    print("  8. Worker FAILS if config missing (no fallback)")
    print("")
    print("SIP Headers (set by Twilio webhook):")
    print("  X-LK-TenantId: tenant identifier")
    print("  X-LK-CallId: unique call identifier")
    print("  X-LK-CalledNumber: phone number that was called")
    print("")
    print("Configuration:")
    print(f"  num_idle_processes: 1 (prevents VAD thread contention)")
    print(f"  OMP_NUM_THREADS: 1 (single-threaded ONNX inference)")
    print("=" * 70)

    # Windows IPC warning suppressor
    if sys.platform == "win32":
        class WindowsIPCFilter(logging.Filter):
            def filter(self, record):
                msg = record.getMessage()
                return not ("DuplexClosed" in msg or "Error in _read_ipc_task" in msg)

        logging.getLogger("livekit.agents").addFilter(WindowsIPCFilter())
        print("NOTE: Running on Windows — IPC watcher warnings suppressed.\n")

    try:
        # Start the worker with limited processes to prevent VAD slowness
        # num_idle_processes=1: Only keep 1 idle process (prevents CPU contention)
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
                prewarm_fnc=prewarm_vad,
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET,
                ws_url=LIVEKIT_URL,
                # IMPORTANT: agent_name MUST match dispatch rule's agentName
                agent_name=AGENT_NAME,
                # Limit to 1 idle process to prevent CPU contention
                num_idle_processes=1,
            )
        )

    except KeyboardInterrupt:
        print("\n\n✓ Worker stopped by user.")
        # Graceful shutdown of Redis
        import asyncio
        from app.core.async_redis import async_redis_client

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(async_redis_client.close())
            else:
                loop.run_until_complete(async_redis_client.close())
        except Exception as e:
            print(f"Warning: Redis cleanup failed: {e}")

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN WORKER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
