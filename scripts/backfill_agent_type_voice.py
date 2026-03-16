"""
One-time migration script:
Backfill missing `agent_type` on legacy voice agents to "voice".
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.firebase import firebase_service


def main() -> None:
    if not getattr(firebase_service, "_initialized", False) or firebase_service.db is None:
        raise RuntimeError("Firebase is not initialized. Check environment configuration before running this script.")

    agents_ref = firebase_service.db.collection("agents")
    docs = list(agents_ref.stream())

    scanned = 0
    updated = 0
    skipped = 0

    for doc in docs:
        scanned += 1
        data = doc.to_dict() or {}
        if data.get("agent_type"):
            skipped += 1
            continue

        doc.reference.update({"agent_type": "voice", "updated_at": datetime.now(timezone.utc).isoformat()})
        updated += 1

    print(
        f"Backfill complete. scanned={scanned}, updated={updated}, skipped={skipped}, "
        "applied_field=agent_type:'voice'"
    )


if __name__ == "__main__":
    main()
