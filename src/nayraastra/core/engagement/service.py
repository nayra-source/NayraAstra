"""Engagement management service."""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from nayraastra.core.audit.models import AuditEventType
from nayraastra.core.domain.models import Engagement, RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.time_id import Clock
from nayraastra.core.engagement.index import update_index_entry
from nayraastra.core.errors import ValidationFailure
from nayraastra.core.paths import validate_engagement_id
from nayraastra.core.ports import (
    EngagementRepository,
    ScopeRepository,
    WorkspaceProvider,
)

if TYPE_CHECKING:
    from nayraastra.core.audit.logger import AuditLogger


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return cleaned[:48] if cleaned else "engagement"


class EngagementService:
    """Orchestrates engagement lifecycle, scope tracking, and auditing."""

    def __init__(
        self,
        repo: EngagementRepository,
        scope_repo: ScopeRepository,
        audit_logger: AuditLogger,
        workspace_provider: WorkspaceProvider,
        clock: Clock,
        home_dir: Path | None = None,
    ) -> None:
        self.repo = repo
        self.scope_repo = scope_repo
        self.audit = audit_logger
        self.workspace_provider = workspace_provider
        self.clock = clock
        self.home_dir = home_dir

    def create(
        self,
        name: str,
        client: str,
        auth_reference: str,
        roe: RulesOfEngagement | None = None,
        scope_entries: list[ScopeEntry] | None = None,
    ) -> Engagement:
        """Create and initialize a new engagement.

        Parameters
        ----------
        name:
            Human-friendly name of the engagement.
        client:
            Organization or target owner.
        auth_reference:
            Mandatory authorization letter / ticket ID proving permission to test.
        roe:
            Rules of engagement policy constraints.
        scope_entries:
            Initial scope rules (at least one in-scope entry required).
        """
        if not name or not name.strip():
            raise ValidationFailure("Engagement name cannot be empty.")

        if not auth_reference or not auth_reference.strip():
            raise ValidationFailure(
                "Authorization reference (written permission / contract id) is mandatory."
            )

        entries = list(scope_entries or [])
        if not any(e.in_scope for e in entries):
            raise ValidationFailure("Engagement must have at least one in-scope target entry.")

        # Generate slugged, safe engagement ID
        slug = _slugify(name)
        suffix = secrets.token_hex(3)
        engagement_id = f"{slug}-{suffix}"
        validate_engagement_id(engagement_id)

        now = self.clock.now()
        effective_roe = roe or RulesOfEngagement()

        engagement = Engagement(
            id=engagement_id,
            name=name.strip(),
            client=client.strip(),
            auth_reference=auth_reference.strip(),
            roe=effective_roe,
            status="active",
            created_at=now,
            updated_at=now,
        )

        # Ensure workspace directories
        self.workspace_provider.get_workspace_dir(engagement_id)
        self.workspace_provider.get_artifacts_dir(engagement_id)
        self.workspace_provider.get_logs_dir(engagement_id)

        # Persist engagement
        self.repo.save(engagement)

        # Persist scope entries
        for entry in entries:
            # Re-bind engagement_id if needed
            entry_to_save = ScopeEntry(
                id=entry.id,
                engagement_id=engagement_id,
                kind=entry.kind,
                value=entry.value,
                in_scope=entry.in_scope,
                note=entry.note,
                created_at=entry.created_at or now,
            )
            self.scope_repo.add_entry(entry_to_save)

        # Audit events
        self.audit.log(
            event_type=AuditEventType.ENGAGEMENT_CREATED,
            entity_type="engagement",
            entity_id=engagement_id,
            payload={
                "name": engagement.name,
                "client": engagement.client,
                "auth_reference": engagement.auth_reference,
                "status": engagement.status,
                "scope_count": len(entries),
            },
        )

        for entry in entries:
            self.audit.log(
                event_type=AuditEventType.SCOPE_ADDED,
                entity_type="scope_entry",
                entity_id=str(entry.value),
                payload={
                    "engagement_id": engagement_id,
                    "kind": entry.kind.value,
                    "value": entry.value,
                    "in_scope": entry.in_scope,
                },
            )

        # Update global index
        if self.home_dir:
            update_index_entry(
                self.home_dir,
                engagement_id=engagement_id,
                name=engagement.name,
                client=engagement.client,
                status=engagement.status,
                created_at=engagement.created_at,
                updated_at=engagement.updated_at,
            )

        return engagement

    def open(self, engagement_id: str) -> Engagement:
        """Open an existing engagement and record an audit log event."""
        validate_engagement_id(engagement_id)
        eng = self.repo.get(engagement_id)
        if not eng:
            raise ValidationFailure(
                f"Engagement {engagement_id!r} not found.",
                details={"engagement_id": engagement_id},
            )

        self.audit.log(
            event_type=AuditEventType.ENGAGEMENT_OPENED,
            entity_type="engagement",
            entity_id=engagement_id,
            payload={"status": eng.status},
        )
        return eng

    def close(self, engagement_id: str) -> Engagement:
        """Close an engagement, setting its status to completed (read-only)."""
        validate_engagement_id(engagement_id)
        eng = self.open(engagement_id)
        now = self.clock.now()

        self.repo.update_status(engagement_id, "completed", now)

        self.audit.log(
            event_type=AuditEventType.ENGAGEMENT_CLOSED,
            entity_type="engagement",
            entity_id=engagement_id,
            payload={"previous_status": eng.status, "new_status": "completed"},
        )

        closed_eng = Engagement(
            id=eng.id,
            name=eng.name,
            client=eng.client,
            auth_reference=eng.auth_reference,
            description=eng.description,
            status="completed",
            roe=eng.roe,
            created_at=eng.created_at,
            updated_at=now,
        )

        if self.home_dir:
            update_index_entry(
                self.home_dir,
                engagement_id=closed_eng.id,
                name=closed_eng.name,
                client=closed_eng.client,
                status="completed",
                updated_at=now,
            )

        return closed_eng

    def list(self) -> list[Engagement]:
        """List all engagements."""
        return self.repo.list_all()

    def add_scope_entry(self, engagement_id: str, entry: ScopeEntry) -> ScopeEntry:
        """Add a scope rule to an active engagement."""
        eng = self.open(engagement_id)
        if eng.status != "active":
            raise ValidationFailure(f"Cannot modify closed engagement (status={eng.status!r}).")

        saved = self.scope_repo.add_entry(entry)
        self.audit.log(
            event_type=AuditEventType.SCOPE_ADDED,
            entity_type="scope_entry",
            entity_id=str(saved.id or saved.value),
            payload={
                "engagement_id": engagement_id,
                "kind": saved.kind.value,
                "value": saved.value,
                "in_scope": saved.in_scope,
            },
        )
        return saved

    def remove_scope_entry(self, engagement_id: str, entry_id: int | str) -> bool:
        """Remove a scope rule from an active engagement."""
        eng = self.open(engagement_id)
        if eng.status != "active":
            raise ValidationFailure(f"Cannot modify closed engagement (status={eng.status!r}).")

        removed = self.scope_repo.remove_entry(entry_id, engagement_id)
        if removed:
            self.audit.log(
                event_type=AuditEventType.SCOPE_REMOVED,
                entity_type="scope_entry",
                entity_id=str(entry_id),
                payload={"engagement_id": engagement_id},
            )
        return removed

    def update_roe(self, engagement_id: str, roe: RulesOfEngagement) -> Engagement:
        """Update rules of engagement for an active engagement."""
        eng = self.open(engagement_id)
        if eng.status != "active":
            raise ValidationFailure(f"Cannot modify closed engagement (status={eng.status!r}).")

        now = self.clock.now()
        self.repo.update_roe(engagement_id, roe, now)
        self.audit.log(
            event_type=AuditEventType.ROE_UPDATED,
            entity_type="roe",
            entity_id=engagement_id,
            payload={
                "max_intrusiveness": roe.max_intrusiveness.value,
                "disruptive_enabled": roe.disruptive_enabled,
                "window_start": roe.window_start.isoformat() if roe.window_start else None,
                "window_end": roe.window_end.isoformat() if roe.window_end else None,
            },
        )
        return self.open(engagement_id)
