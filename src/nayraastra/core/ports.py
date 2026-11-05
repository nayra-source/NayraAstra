"""Repository, sink, and provider ports (interfaces) for NAYRAASTRA.

All ports are defined as `typing.Protocol` classes. The `core` layer depends
only on these protocols; concrete implementations reside in the `db` layer
or the composition root.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict

from nayraastra.core.domain.models import (
    ArtifactRecord,
    Engagement,
    Observation,
    RulesOfEngagement,
    ScopeEntry,
    Task,
)
from nayraastra.core.domain.time_id import Clock
from nayraastra.core.domain.types import Capability, Intrusiveness, TaskStatus

if TYPE_CHECKING:
    from nayraastra.core.audit.models import AuditEntry


class RunContext(BaseModel):
    """Execution environment passed to an adapter at runtime."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    workspace_dir: Path
    artifacts_dir: Path
    clock: Clock
    emit_output: Callable[[str], None]
    timeout_seconds: float = 300.0
    cancel_event: asyncio.Event | None = None


class ToolAdapterPort(Protocol):
    """Port interface representing an external or synthetic security tool adapter."""

    name: str
    capabilities: frozenset[Capability]
    intrusiveness: Intrusiveness

    def check_installed(self) -> Any: ...
    def estimate(self, task: Task) -> Any: ...
    def build_command(self, task: Task) -> list[str]: ...
    async def run(self, task: Task, ctx: RunContext) -> Any: ...
    def parse_output(self, task: Task, raw: Any) -> list[Observation]: ...
    def extract_artifacts(
        self, task: Task, raw: Any, artifacts_dir: Path
    ) -> list[ArtifactRecord]: ...


class AdapterRegistryPort(Protocol):
    """Port interface for adapter discovery, lookup, and capability queries."""

    def register(self, adapter: Any) -> None: ...
    def get(self, name: str) -> Any: ...
    def for_capability(self, capability: Capability) -> list[Any]: ...
    def list_all(self) -> list[Any]: ...


class EngagementRepository(Protocol):
    """Persistence port for engagements."""

    def save(self, engagement: Engagement) -> None:
        """Create or overwrite an engagement record."""
        ...

    def get(self, engagement_id: str) -> Engagement | None:
        """Retrieve an engagement by ID, or None if not found."""
        ...

    def list_all(self) -> list[Engagement]:
        """Return all known engagements."""
        ...

    def update_status(self, engagement_id: str, status: str, updated_at: datetime) -> None:
        """Update engagement lifecycle status."""
        ...

    def update_roe(self, engagement_id: str, roe: RulesOfEngagement, updated_at: datetime) -> None:
        """Update engagement rules of engagement."""
        ...


class ScopeRepository(Protocol):
    """Persistence port for scope entries."""

    def add_entry(self, entry: ScopeEntry) -> ScopeEntry:
        """Persist a new scope entry and return it with assigned ID."""
        ...

    def remove_entry(self, entry_id: int | str, engagement_id: str) -> bool:
        """Delete a scope entry by ID within an engagement."""
        ...

    def list_entries(self, engagement_id: str) -> list[ScopeEntry]:
        """List all scope entries for an engagement."""
        ...


class TaskRepository(Protocol):
    """Persistence port for tasks."""

    def save(self, task: Task) -> None:
        """Create or update a task record."""
        ...

    def get(self, task_id: str) -> Task | None:
        """Retrieve a task by ID."""
        ...

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        exit_code: int | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Update status and runtime details of a task."""
        ...

    def list_by_engagement(
        self, engagement_id: str, status: TaskStatus | None = None
    ) -> list[Task]:
        """List tasks belonging to an engagement, optionally filtered by status."""
        ...

    def find_interrupted(self) -> list[Task]:
        """Find tasks currently stuck in RUNNING status (e.g. after crash)."""
        ...


class ArtifactRepository(Protocol):
    """Persistence port for generated task artifacts."""

    def save(self, artifact: ArtifactRecord) -> None:
        """Persist an artifact metadata record."""
        ...

    def list_by_task(self, task_id: str) -> list[ArtifactRecord]:
        """List artifacts produced by a given task."""
        ...

    def list_by_engagement(self, engagement_id: str) -> list[ArtifactRecord]:
        """List all artifacts for an engagement."""
        ...


class ObservationRepository(Protocol):
    """Persistence port for task observations."""

    def save(self, observation: Observation) -> None:
        """Persist a single observation."""
        ...

    def save_many(self, observations: list[Observation]) -> None:
        """Persist multiple observations in a single operation."""
        ...

    def list_by_task(self, task_id: str) -> list[Observation]:
        """List observations extracted from a task."""
        ...

    def list_by_engagement(self, engagement_id: str) -> list[Observation]:
        """List observations for an engagement."""
        ...


class AuditSink(Protocol):
    """Sink port for appending and verifying immutable audit log records."""

    def write(self, entry: AuditEntry, connection: Any = None) -> AuditEntry:
        """Write an audit entry, optionally inside an existing DB transaction."""
        ...

    def get_last_entry(self) -> AuditEntry | None:
        """Get the latest audit entry in the chain."""
        ...

    def get_all_entries(self) -> list[AuditEntry]:
        """Retrieve all audit entries in historical order."""
        ...


class WorkspaceProvider(Protocol):
    """Port for resolving and preparing filesystem workspaces."""

    def get_workspace_dir(self, engagement_id: str) -> Path:
        """Return root workspace directory for engagement."""
        ...

    def get_artifacts_dir(self, engagement_id: str) -> Path:
        """Return directory for storing engagement artifacts."""
        ...

    def get_logs_dir(self, engagement_id: str) -> Path:
        """Return directory for engagement log files."""
        ...

    def get_db_path(self, engagement_id: str) -> Path:
        """Return path to engagement SQLite database."""
        ...


class Resolver(Protocol):
    """Port for hostname IP resolution (e.g. DNS lookups)."""

    def resolve(self, hostname: str) -> list[str]:
        """Resolve a hostname to a list of IP address strings."""
        ...
