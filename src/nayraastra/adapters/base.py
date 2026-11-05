"""Tool adapter abstract base class and execution context models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from nayraastra.core.domain.models import ArtifactRecord, Observation, Task
from nayraastra.core.domain.types import Capability, Intrusiveness
from nayraastra.core.ports import RunContext

__all__ = [
    "Estimate",
    "RawResult",
    "RunContext",
    "ToolAdapter",
    "ToolStatus",
]


class ToolStatus(BaseModel, frozen=True, extra="forbid"):
    """Installation and readiness status of an external tool."""

    installed: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None


class Estimate(BaseModel, frozen=True, extra="forbid"):
    """Estimated duration and bandwidth footprint of a task."""

    estimated_seconds: float = 0.0
    bandwidth_bytes: int = 0


class RawResult(BaseModel, frozen=True, extra="forbid"):
    """Raw unparsed outcome from an adapter run."""

    exit_code: int
    stdout: bytes = b""
    stderr: bytes = b""
    duration_seconds: float = 0.0
    timed_out: bool = False
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class ToolAdapter(ABC):
    """Abstract interface implemented by all security tool wrappers."""

    name: ClassVar[str]
    capabilities: ClassVar[frozenset[Capability]]
    intrusiveness: ClassVar[Intrusiveness]

    @abstractmethod
    def check_installed(self) -> ToolStatus:
        """Inspect system for required binary and report installation status."""
        ...

    @abstractmethod
    def build_command(self, task: Task) -> list[str]:
        """Construct the argument list to execute. Never return a shell string."""
        ...

    @abstractmethod
    async def run(self, task: Task, ctx: RunContext) -> RawResult:
        """Execute the task and return raw stdout, stderr, and artifacts."""
        ...

    @abstractmethod
    def parse(self, raw: RawResult) -> list[Observation]:
        """Extract structured domain observations from raw execution result."""
        ...

    def estimate(self, task: Task) -> Estimate:
        """Estimate execution resource requirements."""
        return Estimate()
