"""Domain enums and state machines for NAYRAASTRA.

This module defines core types such as Intrusiveness, Capability, TaskStatus,
and state machine rules for task transitions.
"""

from __future__ import annotations

from enum import StrEnum

from nayraastra.core.errors import ValidationFailure


class Intrusiveness(StrEnum):
    """Ordered intrusiveness tiers for task execution and rules of engagement.

    Ordering:
        PASSIVE < ACTIVE_SAFE < ACTIVE_INTRUSIVE < DISRUPTIVE
    """

    PASSIVE = "passive"
    ACTIVE_SAFE = "active-safe"
    ACTIVE_INTRUSIVE = "active-intrusive"
    DISRUPTIVE = "disruptive"

    @property
    def rank(self) -> int:
        ranks = {
            Intrusiveness.PASSIVE: 0,
            Intrusiveness.ACTIVE_SAFE: 1,
            Intrusiveness.ACTIVE_INTRUSIVE: 2,
            Intrusiveness.DISRUPTIVE: 3,
        }
        return ranks[self]

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Intrusiveness):
            return self.rank < other.rank
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Intrusiveness):
            return self.rank <= other.rank
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Intrusiveness):
            return self.rank > other.rank
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Intrusiveness):
            return self.rank >= other.rank
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Intrusiveness):
            return self.rank == other.rank
        if isinstance(other, str):
            return self.value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)


class Capability(StrEnum):
    """Supported capabilities that adapters provide and tasks request."""

    HOST_DISCOVERY = "host_discovery"
    PORT_SCAN = "port_scan"
    SERVICE_DETECT = "service_detect"
    DNS_LOOKUP = "dns_lookup"
    HTTP_PROBE = "http_probe"
    PCAP_ANALYSIS = "pcap_analysis"
    GENERATE_REPORT = "generate_report"


class TaskStatus(StrEnum):
    """Lifecycle status of a scheduled task."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED, TaskStatus.SKIPPED}
    ),
    TaskStatus.RUNNING: frozenset({TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.SKIPPED: frozenset(),
    TaskStatus.BLOCKED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """Return True if transitioning from current to target status is valid."""
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Raise ValidationFailure if status transition is not permitted."""
    if not can_transition(current, target):
        raise ValidationFailure(
            f"Illegal task transition from {current.value!r} to {target.value!r}.",
            details={"current_status": current.value, "target_status": target.value},
        )


class TargetKind(StrEnum):
    """Types of normalized targets."""

    IP = "ip"
    CIDR = "cidr"
    DOMAIN = "domain"
    URL_HOST = "url_host"


class ScopeEntryKind(StrEnum):
    """Types of scope rules."""

    IP = "ip"
    CIDR = "cidr"
    DOMAIN = "domain"
    WILDCARD_DOMAIN = "wildcard_domain"
    URL_HOST = "url_host"
