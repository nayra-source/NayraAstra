"""Task authorizer and rules-of-engagement evaluation gate.

Combines target scope verification with rules of engagement constraints:
- Active engagement lifecycle status
- Authorized testing time window
- Intrusiveness ceiling check
- Disruptive task double opt-in verification
- Capability restriction policy
- Scope check (in-scope required, explicit out-of-scope veto, DNS rebinding checks)

All violations are collected and returned simultaneously.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from nayraastra.core.config import SafetyConfig
from nayraastra.core.domain.models import Engagement, Target
from nayraastra.core.domain.time_id import Clock
from nayraastra.core.domain.types import Capability, Intrusiveness
from nayraastra.core.scope.guard import ScopeDecision, ScopeGuard


class AuthorizationDecision(BaseModel, frozen=True, extra="forbid"):
    """Comprehensive authorization verdict for a candidate task."""

    allowed: bool
    scope_decision: ScopeDecision
    violations: list[str] = Field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.allowed:
            return "Task authorized."
        return "; ".join(self.violations)


class TaskAuthorizer:
    """Rules gate checking all security and operational constraints before task execution."""

    def __init__(
        self,
        clock: Clock,
        safety_config: SafetyConfig | None = None,
    ) -> None:
        self.clock = clock
        self.safety_config = safety_config or SafetyConfig()

    def authorize(
        self,
        engagement: Engagement,
        scope_guard: ScopeGuard,
        target: Target,
        capability: Capability,
        intrusiveness: Intrusiveness,
        resolved_ips: list[str] | None = None,
    ) -> AuthorizationDecision:
        """Evaluate task parameters against ROE and scope policy."""
        violations: list[str] = []

        # 1. Engagement Status Check
        if engagement.status != "active":
            violations.append(f"Engagement is not active (current status: {engagement.status!r}).")

        # 2. Time Window Check
        now = self.clock.now()
        roe = engagement.roe

        if roe.window_start is not None and now < roe.window_start:
            violations.append(
                f"Current time ({now.isoformat()}) is before engagement window_start ({roe.window_start.isoformat()})."
            )

        if roe.window_end is not None and now > roe.window_end:
            violations.append(
                f"Current time ({now.isoformat()}) is after engagement window_end ({roe.window_end.isoformat()})."
            )

        # 3. Intrusiveness Ceiling Check
        if intrusiveness > roe.max_intrusiveness:
            violations.append(
                f"Task intrusiveness ({intrusiveness.value}) exceeds engagement maximum ({roe.max_intrusiveness.value})."
            )

        if intrusiveness > self.safety_config.max_intrusiveness:
            violations.append(
                f"Task intrusiveness ({intrusiveness.value}) exceeds global safety ceiling ({self.safety_config.max_intrusiveness.value})."
            )

        # 4. Disruptive Double Opt-In Check
        if intrusiveness == Intrusiveness.DISRUPTIVE:
            if not roe.disruptive_enabled:
                violations.append(
                    "Disruptive tasks require disruptive_enabled=True on the engagement."
                )
            if not self.safety_config.disruptive_enabled:
                violations.append(
                    "Disruptive tasks require disruptive_enabled=True in global SafetyConfig."
                )

        # 5. Capability Restriction Check
        if roe.allowed_capabilities is not None and capability not in roe.allowed_capabilities:
            violations.append(
                f"Capability {capability.value!r} is not allowed by engagement rules of engagement."
            )

        # 6. Scope Guard Verification
        scope_decision = scope_guard.check(target, resolved_ips=resolved_ips)
        if not scope_decision.allowed:
            violations.extend(scope_decision.violations)

        is_allowed = len(violations) == 0
        return AuthorizationDecision(
            allowed=is_allowed,
            scope_decision=scope_decision,
            violations=violations,
        )
