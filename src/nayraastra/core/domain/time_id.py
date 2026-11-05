"""Injectable time and ID generation protocols for NAYRAASTRA.

Services must never call `datetime.now()` or `uuid.uuid4()` directly,
enabling fully deterministic and time-travel testing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol for getting timezone-aware UTC datetime."""

    def now(self) -> datetime:
        """Return the current datetime (always timezone-aware in UTC)."""
        ...


class UtcClock:
    """Standard Clock returning real-time UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic Clock for testing that returns a fixed datetime."""

    def __init__(self, fixed_time: datetime | None = None) -> None:
        if fixed_time is None:
            self._time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        elif fixed_time.tzinfo is None:
            self._time = fixed_time.replace(tzinfo=UTC)
        else:
            self._time = fixed_time.astimezone(UTC)

    def now(self) -> datetime:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += timedelta(seconds=seconds)

    def set_time(self, new_time: datetime) -> None:
        if new_time.tzinfo is None:
            self._time = new_time.replace(tzinfo=UTC)
        else:
            self._time = new_time.astimezone(UTC)


@runtime_checkable
class IdGenerator(Protocol):
    """Protocol for generating unique entity identifiers."""

    def generate(self) -> str:
        """Generate a unique identifier string."""
        ...


class UuidGenerator:
    """Standard generator using random UUIDv4."""

    def generate(self) -> str:
        return str(uuid.uuid4())


class StaticIdGenerator:
    """Deterministic ID generator for testing."""

    def __init__(self, ids: list[str] | None = None, prefix: str = "id") -> None:
        self._ids = list(ids) if ids else []
        self._prefix = prefix
        self._counter = 0

    def generate(self) -> str:
        if self._ids:
            return self._ids.pop(0)
        self._counter += 1
        return f"{self._prefix}-{self._counter:04d}"
