"""
Backfill script for telephony ownership fields on phone_numbers.

Usage:
    python scripts/backfill_phone_usage_roles.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("PYTHONPATH", str(ROOT_DIR))

from app.services.firebase import firebase_service  # noqa: E402


async def run() -> None:
    if not firebase_service.db:
        raise RuntimeError("Firebase is not configured")

    def _fetch_all():
        return list(firebase_service.db.collection("phone_numbers").stream())

    docs = await firebase_service._run_in_executor(_fetch_all)
    updated = 0
    skipped = 0

    for doc in docs:
        payload = doc.to_dict() or {}
        if payload.get("usage_role"):
            skipped += 1
            continue

        status = payload.get("status", "active")
        role_status = "active" if status == "active" else "inactive"
        await firebase_service.update_phone_number(
            doc.id,
            {
                "usage_role": "voice_agent_inbound",
                "role_status": role_status,
                "conflict_code": None,
                "conflict_message": None,
            },
        )
        updated += 1

    print(f"phone_numbers scanned={len(docs)} updated={updated} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(run())
