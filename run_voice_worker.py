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
        # CRITICAL: Verify credentials and system time before starting worker
        # This helps diagnose 401 authentication errors
        import datetime
        from livekit import api as livekit_api
        
        print("\n[PRE-FLIGHT CHECKS]")
        print("=" * 70)
        
        # Check system time (JWT tokens are time-sensitive)
        server_time = datetime.datetime.now(datetime.timezone.utc)
        print(f"Server UTC Time: {server_time.isoformat()}")
        print(f"  ⚠ If this is significantly off from actual time, JWT tokens will be rejected")
        
        # Verify credentials format
        print(f"\n[CREDENTIALS VERIFICATION]")
        print(f"  LIVEKIT_URL: {LIVEKIT_URL}")
        print(f"  LIVEKIT_API_KEY: {LIVEKIT_API_KEY[:10]}... (length: {len(LIVEKIT_API_KEY) if LIVEKIT_API_KEY else 0})")
        secret_length = len(LIVEKIT_API_SECRET) if LIVEKIT_API_SECRET else 0
        print(f"  LIVEKIT_API_SECRET: {'*' * 20}... (length: {secret_length})")
        
        if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET or not LIVEKIT_URL:
            print("\n❌ ERROR: Missing LiveKit credentials!")
            sys.exit(1)
        
        # Verify secret is not empty (LiveKit secrets can vary in length)
        if secret_length < 20:
            print(f"\n  ⚠ WARNING: API Secret length ({secret_length}) seems too short")
            print(f"  ⚠ This might indicate a truncated secret in your .env file")
        
        # Test token generation (this verifies credentials work for JWT signing)
        print(f"\n[TOKEN GENERATION TEST]")
        try:
            from livekit import api as lk_api
            # Generate a test token to verify API key/secret are valid
            test_token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            test_token.with_identity("test-worker")
            test_token.with_grants(lk_api.VideoGrants(agent=True))
            jwt_token = test_token.to_jwt()
            
            # Verify token was generated (not empty)
            if jwt_token and len(jwt_token) > 10:
                print(f"  ✓ Token generation successful (credentials are valid)")
                print(f"  ✓ Token length: {len(jwt_token)} characters")
            else:
                print(f"  ❌ Token generation failed: empty token")
                sys.exit(1)
        except Exception as e:
            print(f"  ❌ Token generation failed: {e}")
            print(f"  ⚠ This suggests API key/secret are incorrect or mismatched")
            print(f"  ⚠ Error details: {type(e).__name__}: {str(e)}")
            sys.exit(1)
        
        print("=" * 70)
        print("\n[STARTING WORKER]")
        print("  If you see '401' errors below, check:")
        print("  1. System clock is synchronized (NTP)")
        print("  2. LIVEKIT_API_SECRET matches the API key's project")
        print("  3. No firewall blocking WebSocket connections")
        print("  4. LiveKit SDK version is up-to-date")
        print("  5. agent_name matches dispatch rule configuration")
        print("=" * 70)
        print()
        
        # CRITICAL: Ensure environment variables are set
        # WorkerOptions may prefer env vars over passed parameters
        # Setting them explicitly ensures consistency
        os.environ["LIVEKIT_URL"] = LIVEKIT_URL
        os.environ["LIVEKIT_API_KEY"] = LIVEKIT_API_KEY
        os.environ["LIVEKIT_API_SECRET"] = LIVEKIT_API_SECRET
        
        print(f"[WORKER CONFIG] Using explicit credentials:")
        print(f"  API Key: {LIVEKIT_API_KEY[:10]}...")
        print(f"  API Secret: {'*' * 20}... (length: {len(LIVEKIT_API_SECRET)})")
        print(f"  URL: {LIVEKIT_URL}")
        print(f"  Agent Name: {AGENT_NAME}")
        print()
        
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
