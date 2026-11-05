"""Unit tests for TaskAuthorizer / RulesGate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nayraastra.core.config import SafetyConfig
from nayraastra.core.domain.models import Engagement, RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.time_id import FrozenClock
from nayraastra.core.domain.types import Capability, Intrusiveness, ScopeEntryKind
from nayraastra.core.scope.authorizer import TaskAuthorizer
from nayraastra.core.scope.guard import ScopeGuard
from nayraastra.core.scope.normalize import normalize_target


@pytest.mark.unit
class TestTaskAuthorizer:
    def _setup_authorizer(
        self,
        now: datetime,
        safety_config: SafetyConfig | None = None,
    ) -> tuple[TaskAuthorizer, FrozenClock]:
        clock = FrozenClock(now)
        authorizer = TaskAuthorizer(clock=clock, safety_config=safety_config)
        return authorizer, clock

    def _make_engagement(
        self,
        status: str = "active",
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        max_intrusiveness: Intrusiveness = Intrusiveness.ACTIVE_SAFE,
        disruptive_enabled: bool = False,
        allowed_capabilities: frozenset[Capability] | None = None,
    ) -> Engagement:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        roe = RulesOfEngagement(
            window_start=window_start,
            window_end=window_end,
            max_intrusiveness=max_intrusiveness,
            disruptive_enabled=disruptive_enabled,
            allowed_capabilities=allowed_capabilities,
        )
        return Engagement(
            id="test-eng",
            name="Test",
            client="Acme",
            auth_reference="AUTH-1234",
            status=status,
            roe=roe,
            created_at=now,
            updated_at=now,
        )

    def test_all_checks_pass(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        authorizer, _ = self._setup_authorizer(now)
        eng = self._make_engagement(
            window_start=now - timedelta(hours=1),
            window_end=now + timedelta(hours=1),
            max_intrusiveness=Intrusiveness.ACTIVE_SAFE,
        )
        guard = ScopeGuard(
            [
                ScopeEntry(
                    id=1,
                    engagement_id="test-eng",
                    kind=ScopeEntryKind.IP,
                    value="10.0.0.5",
                    in_scope=True,
                    created_at=now,
                )
            ]
        )
        decision = authorizer.authorize(
            engagement=eng,
            scope_guard=guard,
            target=normalize_target("10.0.0.5"),
            capability=Capability.PORT_SCAN,
            intrusiveness=Intrusiveness.ACTIVE_SAFE,
        )
        assert decision.allowed
        assert len(decision.violations) == 0

    def test_window_boundary_checks(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        authorizer, clock = self._setup_authorizer(now)
        guard = ScopeGuard(
            [
                ScopeEntry(
                    id=1,
                    engagement_id="test-eng",
                    kind=ScopeEntryKind.IP,
                    value="10.0.0.5",
                    in_scope=True,
                    created_at=now,
                )
            ]
        )

        # Before window_start
        eng_future = self._make_engagement(
            window_start=now + timedelta(hours=1),
            window_end=now + timedelta(hours=2),
        )
        d1 = authorizer.authorize(
            eng_future,
            guard,
            normalize_target("10.0.0.5"),
            Capability.PORT_SCAN,
            Intrusiveness.PASSIVE,
        )
        assert not d1.allowed
        assert any("before engagement window_start" in v for v in d1.violations)

        # After window_end
        eng_past = self._make_engagement(
            window_start=now - timedelta(hours=2),
            window_end=now - timedelta(hours=1),
        )
        d2 = authorizer.authorize(
            eng_past,
            guard,
            normalize_target("10.0.0.5"),
            Capability.PORT_SCAN,
            Intrusiveness.PASSIVE,
        )
        assert not d2.allowed
        assert any("after engagement window_end" in v for v in d2.violations)

    def test_intrusiveness_ceiling_and_disruptive_double_optin(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        # Global safety config without disruptive
        authorizer, _ = self._setup_authorizer(
            now, SafetyConfig(max_intrusiveness=Intrusiveness.ACTIVE_SAFE)
        )
        eng = self._make_engagement(max_intrusiveness=Intrusiveness.ACTIVE_SAFE)
        guard = ScopeGuard(
            [
                ScopeEntry(
                    id=1,
                    engagement_id="test-eng",
                    kind=ScopeEntryKind.IP,
                    value="10.0.0.1",
                    in_scope=True,
                    created_at=now,
                )
            ]
        )

        # Exceeds ceiling
        d1 = authorizer.authorize(
            eng,
            guard,
            normalize_target("10.0.0.1"),
            Capability.PORT_SCAN,
            Intrusiveness.ACTIVE_INTRUSIVE,
        )
        assert not d1.allowed
        assert any("exceeds engagement maximum" in v for v in d1.violations)

        # Disruptive without double opt-in
        d2 = authorizer.authorize(
            eng, guard, normalize_target("10.0.0.1"), Capability.PORT_SCAN, Intrusiveness.DISRUPTIVE
        )
        assert not d2.allowed
        assert any("disruptive_enabled=True" in v for v in d2.violations)

    def test_multiple_simultaneous_violations_reported(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        authorizer, _ = self._setup_authorizer(now)
        # Closed engagement + past window + restricted capability
        eng = self._make_engagement(
            status="completed",
            window_start=now - timedelta(days=2),
            window_end=now - timedelta(days=1),
            allowed_capabilities=frozenset({Capability.DNS_LOOKUP}),
        )
        # Out-of-scope target
        guard = ScopeGuard([])

        decision = authorizer.authorize(
            engagement=eng,
            scope_guard=guard,
            target=normalize_target("192.168.1.1"),
            capability=Capability.PORT_SCAN,
            intrusiveness=Intrusiveness.ACTIVE_INTRUSIVE,
        )
        assert not decision.allowed
        # Multiple violations collected at once
        assert len(decision.violations) >= 4
        err_all = "; ".join(decision.violations)
        assert "not active" in err_all
        assert "window_end" in err_all
        assert "Capability" in err_all
        assert "not covered by any in-scope rule" in err_all
