"""Domain entity models for NAYRAASTRA.

All models are Pydantic v2 models with extra="forbid", and frozen where
representing immutable records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nayraastra.core.domain.types import (
    Capability,
    Intrusiveness,
    ScopeEntryKind,
    TargetKind,
    TaskStatus,
)


class Target(BaseModel, frozen=True, extra="forbid"):
    """Normalized target specification for a security operation."""

    raw: str
    normalized: str
    kind: TargetKind
    port: int | None = None
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScopeEntry(BaseModel, frozen=True, extra="forbid"):
    """A single allow or deny rule within an engagement scope."""

    id: int | str | None = None
    engagement_id: str
    kind: ScopeEntryKind
    value: str
    in_scope: bool = True
    note: str = ""
    created_at: datetime


class RulesOfEngagement(BaseModel, frozen=True, extra="forbid"):
    """Rules of engagement governing safety, timing, and intrusiveness."""

    window_start: datetime | None = None
    window_end: datetime | None = None
    max_intrusiveness: Intrusiveness = Intrusiveness.ACTIVE_SAFE
    disruptive_enabled: bool = False
    allowed_capabilities: frozenset[Capability] | None = None


class Engagement(BaseModel, frozen=True, extra="forbid"):
    """A discrete pentesting engagement."""

    id: str
    name: str
    client: str = ""
    auth_reference: str = ""
    description: str = ""
    status: str = "active"
    roe: RulesOfEngagement = Field(default_factory=RulesOfEngagement)
    created_at: datetime
    updated_at: datetime


class Task(BaseModel, frozen=True, extra="forbid"):
    """A scheduled or executed unit of work delegated to an adapter."""

    id: str
    engagement_id: str
    workflow_run_id: int | None = None
    module_name: str
    adapter_name: str
    capability: Capability
    target: Target
    status: TaskStatus = TaskStatus.PENDING
    intrusiveness: Intrusiveness = Intrusiveness.PASSIVE
    args: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    error_message: str | None = None
    created_at: datetime


class ArtifactRecord(BaseModel, frozen=True, extra="forbid"):
    """Record of a raw file generated during task execution."""

    id: int | str | None = None
    task_id: str
    engagement_id: str
    artifact_type: str = "raw_output"
    mime_type: str = "text/plain"
    path: str
    size_bytes: int = 0
    sha256: str = ""
    tool: str = ""
    tool_version: str = ""
    command_line: list[str] = Field(default_factory=list)
    created_at: datetime


class Observation(BaseModel, frozen=True, extra="forbid"):
    """Structured finding or observation extracted from an artifact."""

    id: int | str | None = None
    task_id: str
    engagement_id: str
    host_id: int | None = None
    observation_key: str
    value: dict[str, Any]
    confidence: str = "likely"
    source_task_id: str | None = None
    observed_at: datetime


class TaskResult(BaseModel, frozen=True, extra="forbid"):
    """Aggregated outcome of executing a task."""

    task_id: str
    status: TaskStatus
    exit_code: int | None = None
    error_message: str | None = None
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
