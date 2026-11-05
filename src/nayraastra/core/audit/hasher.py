"""Deterministic hash-chain calculation for audit log records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_entry_hash(
    *,
    logged_at: str,
    event_type: str,
    actor: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    """Compute SHA-256 digest over canonical JSON representation + prev_hash."""
    canonical = {
        "actor": str(actor),
        "entity_id": str(entity_id),
        "entity_type": str(entity_type),
        "event_type": str(event_type),
        "logged_at": str(logged_at),
        "payload": payload,
        "prev_hash": str(prev_hash),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
