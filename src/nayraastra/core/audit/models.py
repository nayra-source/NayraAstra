"""Audit log data models and known event types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AuditEventType(StrEnum):
    """Canonical event types for audit logging."""

    ENGAGEMENT_CREATED = "engagement.created"
    ENGAGEMENT_OPENED = "engagement.opened"
    ENGAGEMENT_CLOSED = "engagement.closed"
    SCOPE_ADDED = "scope.added"
    SCOPE_REMOVED = "scope.removed"
    ROE_UPDATED = "roe.updated"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"
    TASK_BLOCKED = "task.blocked"
    TASK_CANCELLED = "task.cancelled"
    TASK_DRY_RUN = "task.dry_run"
    POLICY_DENIED = "policy.denied"
    ADAPTER_REGISTERED = "adapter.registered"


class AuditEntry(BaseModel, frozen=True, extra="forbid"):
    """Immutable, hash-chained record in the audit trail."""

    id: int | None = None
    event_type: str
    actor: str = "system"
    entity_type: str = ""
    entity_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    logged_at: str
    prev_hash: str = "0" * 64
    entry_hash: str = ""


class ChainReport(BaseModel, frozen=True, extra="forbid"):
    """Result of audit trail integrity verification."""

    valid: bool
    count: int
    first_broken_index: int | None = None
    error_message: str | None = None
