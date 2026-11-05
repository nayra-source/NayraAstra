"""Typed in-process event definitions for NAYRAASTRA.

All text fields are automatically sanitized to strip control characters
and ANSI escape sequences before publication.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Re-use control char regex to strip ANSI and control characters
_CONTROL_RE = re.compile(
    r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]" r"|\x1B[@-Z\\-_]" r"|[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"
)


def sanitize_text(text: str) -> str:
    """Strip ANSI escape sequences and non-printable control characters."""
    if not isinstance(text, str):
        return str(text)
    return _CONTROL_RE.sub("", text)


class BaseEvent(BaseModel, frozen=True, extra="forbid"):
    """Base class for all domain events."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EngagementOpened(BaseEvent):
    type: Literal["engagement.opened"] = "engagement.opened"
    engagement_id: str


class TaskQueued(BaseEvent):
    type: Literal["task.queued"] = "task.queued"
    task_id: str
    engagement_id: str
    module_name: str
    adapter_name: str
    target: str


class TaskStarted(BaseEvent):
    type: Literal["task.started"] = "task.started"
    task_id: str
    engagement_id: str
    command_line: list[str] = Field(default_factory=list)


class TaskOutput(BaseEvent):
    type: Literal["task.output"] = "task.output"
    task_id: str
    engagement_id: str
    line: str

    @field_validator("line", mode="before")
    @classmethod
    def _clean_line(cls, v: Any) -> str:
        return sanitize_text(str(v))


class TaskSucceeded(BaseEvent):
    type: Literal["task.succeeded"] = "task.succeeded"
    task_id: str
    engagement_id: str
    exit_code: int = 0
    artifacts_count: int = 0
    observations_count: int = 0


class TaskFailed(BaseEvent):
    type: Literal["task.failed"] = "task.failed"
    task_id: str
    engagement_id: str
    error_message: str

    @field_validator("error_message", mode="before")
    @classmethod
    def _clean_err(cls, v: Any) -> str:
        return sanitize_text(str(v))


class TaskBlocked(BaseEvent):
    type: Literal["task.blocked"] = "task.blocked"
    task_id: str
    engagement_id: str
    reason: str

    @field_validator("reason", mode="before")
    @classmethod
    def _clean_reason(cls, v: Any) -> str:
        return sanitize_text(str(v))


class ScopeViolation(BaseEvent):
    type: Literal["scope.violation"] = "scope.violation"
    engagement_id: str
    target: str
    violations: list[str] = Field(default_factory=list)

    @field_validator("target", mode="before")
    @classmethod
    def _clean_target(cls, v: Any) -> str:
        return sanitize_text(str(v))


class ToolMissing(BaseEvent):
    type: Literal["tool.missing"] = "tool.missing"
    tool_name: str
    adapter_name: str
    error_message: str

    @field_validator("error_message", mode="before")
    @classmethod
    def _clean_msg(cls, v: Any) -> str:
        return sanitize_text(str(v))


Event = (
    EngagementOpened
    | TaskQueued
    | TaskStarted
    | TaskOutput
    | TaskSucceeded
    | TaskFailed
    | TaskBlocked
    | ScopeViolation
    | ToolMissing
)
