"""SQLite implementation of ScopeRepository."""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import UTC, datetime

from nayraastra.core.domain.models import ScopeEntry
from nayraastra.core.domain.types import ScopeEntryKind
from nayraastra.core.errors import DatabaseError


def _parse_utc(dt_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class SqliteScopeRepository:
    """Stores and retrieves scope entries."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_entry(self, entry: ScopeEntry) -> ScopeEntry:
        """Insert a scope entry and return with new rowid."""
        query = """
            INSERT INTO scope_entries (
                engagement_id, entry_type, value, description, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """
        entry_type = "allow" if entry.in_scope else "deny"
        # Store kind in description if not explicitly set
        desc = entry.note or f"kind={entry.kind.value}"
        try:
            cursor = self.conn.execute(
                query,
                (
                    entry.engagement_id,
                    entry_type,
                    entry.value,
                    desc,
                    entry.created_at.isoformat(),
                ),
            )
            self.conn.commit()
            assigned_id = cursor.lastrowid
            return ScopeEntry(
                id=assigned_id,
                engagement_id=entry.engagement_id,
                kind=entry.kind,
                value=entry.value,
                in_scope=entry.in_scope,
                note=entry.note,
                created_at=entry.created_at,
            )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to add scope entry {entry.value}: {exc}") from exc

    def remove_entry(self, entry_id: int | str, engagement_id: str) -> bool:
        """Remove a scope entry by ID."""
        query = "DELETE FROM scope_entries WHERE id = ? AND engagement_id = ?"
        try:
            cursor = self.conn.execute(query, (int(entry_id), engagement_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to remove scope entry {entry_id}: {exc}") from exc

    def list_entries(self, engagement_id: str) -> list[ScopeEntry]:
        """List all scope rules for an engagement."""
        query = "SELECT * FROM scope_entries WHERE engagement_id = ? ORDER BY id"
        try:
            rows = self.conn.execute(query, (engagement_id,)).fetchall()
            results: list[ScopeEntry] = []
            for row in rows:
                val = row["value"]
                desc = row["description"] or ""

                # Infer kind from value or desc
                kind = ScopeEntryKind.DOMAIN
                if "/" in val:
                    kind = ScopeEntryKind.CIDR
                elif val.startswith("*."):
                    kind = ScopeEntryKind.WILDCARD_DOMAIN
                elif any(c.isdigit() for c in val) and ":" not in val and "." in val:
                    parts = val.split(".")
                    if len(parts) == 4 and all(p.isdigit() for p in parts):
                        kind = ScopeEntryKind.IP
                elif ":" in val:
                    kind = ScopeEntryKind.IP

                if "kind=" in desc:
                    for part in desc.split(";"):
                        if part.strip().startswith("kind="):
                            k_val = part.strip()[len("kind=") :]
                            with contextlib.suppress(ValueError):
                                kind = ScopeEntryKind(k_val)

                results.append(
                    ScopeEntry(
                        id=row["id"],
                        engagement_id=row["engagement_id"],
                        kind=kind,
                        value=val,
                        in_scope=(row["entry_type"] == "allow"),
                        note=desc,
                        created_at=_parse_utc(row["created_at"]),
                    )
                )
            return results
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to list scope entries for {engagement_id}: {exc}") from exc
