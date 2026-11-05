"""Audit logger that redacts, timestamps, hash-chains, and writes entries."""

from __future__ import annotations

import getpass
from typing import Any

from nayraastra.core.audit.hasher import compute_entry_hash
from nayraastra.core.audit.models import AuditEntry, AuditEventType
from nayraastra.core.audit.redaction import redact_data
from nayraastra.core.domain.time_id import Clock
from nayraastra.core.ports import AuditSink

GENESIS_HASH = "0" * 64


class AuditLogger:
    """Service for appending securely chained, redacted audit events."""

    def __init__(
        self,
        sink: AuditSink,
        clock: Clock,
        default_actor: str | None = None,
    ) -> None:
        self.sink = sink
        self.clock = clock
        if default_actor is not None:
            self.default_actor = default_actor
        else:
            try:
                self.default_actor = getpass.getuser()
            except Exception:
                self.default_actor = "system"

    def log(
        self,
        event_type: str | AuditEventType,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
        connection: Any = None,
    ) -> AuditEntry:
        """Record an audit event into the tamper-evident chain."""
        ev_str = event_type.value if isinstance(event_type, AuditEventType) else str(event_type)
        act_str = actor or self.default_actor
        timestamp = self.clock.now().isoformat()
        clean_payload = redact_data(payload or {})

        # Query previous hash from the sink
        last_entry = self.sink.get_last_entry()
        prev_hash = last_entry.entry_hash if last_entry and last_entry.entry_hash else GENESIS_HASH

        entry_hash = compute_entry_hash(
            logged_at=timestamp,
            event_type=ev_str,
            actor=act_str,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=clean_payload,
            prev_hash=prev_hash,
        )

        entry = AuditEntry(
            event_type=ev_str,
            actor=act_str,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=clean_payload,
            logged_at=timestamp,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

        persisted = self.sink.write(entry, connection=connection)
        return persisted or entry
