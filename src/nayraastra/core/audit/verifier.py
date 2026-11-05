"""Audit log chain verification."""

from __future__ import annotations

from nayraastra.core.audit.hasher import compute_entry_hash
from nayraastra.core.audit.logger import GENESIS_HASH
from nayraastra.core.audit.models import AuditEntry, ChainReport


def verify_chain(entries: list[AuditEntry]) -> ChainReport:
    """Verify cryptographic integrity of an audit entry sequence."""
    if not entries:
        return ChainReport(valid=True, count=0)

    for i, entry in enumerate(entries):
        # 1. Verify prev_hash matches preceding entry
        expected_prev = GENESIS_HASH if i == 0 else entries[i - 1].entry_hash

        if entry.prev_hash != expected_prev:
            return ChainReport(
                valid=False,
                count=len(entries),
                first_broken_index=i,
                error_message=(
                    f"Chain broken at index {i}: expected prev_hash {expected_prev!r}, "
                    f"got {entry.prev_hash!r} (entry id={entry.id})"
                ),
            )

        # 2. Verify entry_hash matches recalculation
        expected_hash = compute_entry_hash(
            logged_at=entry.logged_at,
            event_type=entry.event_type,
            actor=entry.actor,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
            prev_hash=entry.prev_hash,
        )

        if entry.entry_hash != expected_hash:
            return ChainReport(
                valid=False,
                count=len(entries),
                first_broken_index=i,
                error_message=(
                    f"Content tampered at index {i}: computed hash {expected_hash!r}, "
                    f"stored hash {entry.entry_hash!r} (entry id={entry.id})"
                ),
            )

    return ChainReport(valid=True, count=len(entries))
