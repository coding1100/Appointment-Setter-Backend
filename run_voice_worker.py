# """
# Run the LiveKit Voice Agent Worker
# This script starts the LiveKit agent worker that handles voice interactions.
# """
# import os
# import sys
# import multiprocessing
# from dotenv import load_dotenv

# # Load environment variables BEFORE importing from app.core.config
# load_dotenv()

# from app.agents.voice_worker import entrypoint
# from livekit import agents
# from app.core.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

# if __name__ == "__main__":
#     multiprocessing.freeze_support()
    
#     print("="  * 60)
#     print("Starting LiveKit Voice Agent Worker...")
#     print(f"LiveKit URL: {LIVEKIT_URL}")
    
#     # Check if running on Windows
#     is_windows = sys.platform == "win32"
#     if is_windows:
#         print("Platform: Windows (IPC watcher may have limitations)")
    
#     print("=" * 60)
    
#     # On Windows, suppress IPC watcher errors (known limitation)
#     # The error occurs in a background task and doesn't affect worker functionality
#     import logging
    
#     # Suppress the specific IPC error on Windows
#     if is_windows:
#         # Filter out DuplexClosed errors from logs
#         class WindowsIPCFilter(logging.Filter):
#             def filter(self, record):
#                 # Suppress DuplexClosed errors on Windows
#                 if "DuplexClosed" in str(record.getMessage()) or "Error in _read_ipc_task" in str(record.getMessage()):
#                     return False
#                 return True
        
#         # Apply filter to livekit.agents logger
#         agents_logger = logging.getLogger("livekit.agents")
#         agents_logger.addFilter(WindowsIPCFilter())
        
#         print("Note: IPC watcher has known limitations on Windows.")
#         print("Worker will function normally despite IPC warnings.\n")
    
#     try:
#         # Use WorkerOptions with explicit configuration
#         # This approach works without CLI commands (no "start" needed)
#         agents.cli.run_app(
#             agents.WorkerOptions(
#                 entrypoint_fnc=entrypoint,
#                 api_key=LIVEKIT_API_KEY,
#                 api_secret=LIVEKIT_API_SECRET,
#                 ws_url=LIVEKIT_URL,
#             )
#         )
#     except KeyboardInterrupt:
#         print("\n\n✓ Worker stopped by user")
#         # OPTIMIZATION: Explicitly close Redis connection on shutdown
#         import asyncio
#         from app.core.async_redis import async_redis_client
        
#         loop = asyncio.get_event_loop()
#         if loop.is_running():
#             loop.create_task(async_redis_client.close())
#         else:
#             loop.run_until_complete(async_redis_client.close())
            
#         sys.exit(0)
#     except Exception as e:
#         print(f"\n❌ Fatal error: {e}")
#         import traceback
#         traceback.print_exc()
#         sys.exit(1)

"""
Run the LiveKit Voice Agent Worker
Starts a single worker instance that handles all inbound SIP calls.
"""

import os
import sys
import multiprocessing
import logging
from dotenv import load_dotenv

# Load environment variables before importing config
load_dotenv()

from livekit import agents
from app.agents.voice_worker import entrypoint
from app.core.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL


if __name__ == "__main__":
    multiprocessing.freeze_support()

    print("=" * 70)
    print("Starting LiveKit Voice Agent Worker…")
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print("Worker agent_name: '' (empty, allowed & intentional)")
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
        # Start the worker
        agents.cli.run_app(
            agents.WorkerOptions(
                entrypoint_fnc=entrypoint,
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET,
                ws_url=LIVEKIT_URL,    # must be wss://….livekit.cloud
                agent_name="",         # ← YOU REQUIRE EMPTY NAME (valid)
            )
        )

    except KeyboardInterrupt:
        print("\nWorker stopped by user.")
        # Graceful shutdown of Redis
        import asyncio
        from app.core.async_redis import async_redis_client

        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(async_redis_client.close())
        else:
            loop.run_until_complete(async_redis_client.close())

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN WORKER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

