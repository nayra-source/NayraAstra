"""SQLite implementation of AuditSink."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from nayraastra.core.audit.models import AuditEntry
from nayraastra.core.errors import DatabaseError


def _row_to_audit(row: sqlite3.Row) -> AuditEntry:
    payload = json.loads(row["payload"]) if row["payload"] else {}
    prev_h = row["prev_hash"] if "prev_hash" in row.keys() and row["prev_hash"] else "0" * 64
    entry_h = row["entry_hash"] if "entry_hash" in row.keys() and row["entry_hash"] else ""

    return AuditEntry(
        id=row["id"],
        event_type=row["event_type"],
        actor=row["actor"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        payload=payload,
        logged_at=row["logged_at"],
        prev_hash=prev_h,
        entry_hash=entry_h,
    )


class SqliteAuditSink:
    """Appends immutable audit entries to the SQLite audit_log table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def write(self, entry: AuditEntry, connection: Any = None) -> AuditEntry:
        """Write an audit entry, optionally inside an existing transaction."""
        target_conn = connection or self.conn
        query = """
            INSERT INTO audit_log (
                event_type, actor, entity_type, entity_id, payload,
                logged_at, prev_hash, entry_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            cursor = target_conn.execute(
                query,
                (
                    entry.event_type,
                    entry.actor,
                    entry.entity_type,
                    entry.entity_id,
                    json.dumps(entry.payload),
                    entry.logged_at,
                    entry.prev_hash,
                    entry.entry_hash,
                ),
            )
            if connection is None:
                target_conn.commit()
            return entry.model_copy(update={"id": cursor.lastrowid})
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to append audit log entry: {exc}") from exc

    def get_last_entry(self) -> AuditEntry | None:
        """Retrieve the latest audit entry."""
        query = "SELECT * FROM audit_log ORDER BY id DESC LIMIT 1"
        try:
            row = self.conn.execute(query).fetchone()
            if not row:
                return None
            return _row_to_audit(row)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to query latest audit log: {exc}") from exc

    def get_all_entries(self) -> list[AuditEntry]:
        """Retrieve all audit entries in historical order."""
        query = "SELECT * FROM audit_log ORDER BY id ASC"
        try:
            rows = self.conn.execute(query).fetchall()
            return [_row_to_audit(r) for r in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch audit log entries: {exc}") from exc
