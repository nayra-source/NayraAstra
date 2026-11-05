"""Unit tests for domain types, models, state machine, and injectable clock/id."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nayraastra.core.domain.time_id import (
    FrozenClock,
    StaticIdGenerator,
    UtcClock,
    UuidGenerator,
)
from nayraastra.core.domain.types import (
    Intrusiveness,
    TaskStatus,
    assert_transition,
    can_transition,
)
from nayraastra.core.errors import ValidationFailure


@pytest.mark.unit
class TestIntrusiveness:
    def test_ordering(self) -> None:
        assert Intrusiveness.PASSIVE < Intrusiveness.ACTIVE_SAFE
        assert Intrusiveness.ACTIVE_SAFE < Intrusiveness.ACTIVE_INTRUSIVE
        assert Intrusiveness.ACTIVE_INTRUSIVE < Intrusiveness.DISRUPTIVE
        assert Intrusiveness.PASSIVE <= Intrusiveness.PASSIVE
        assert Intrusiveness.DISRUPTIVE > Intrusiveness.ACTIVE_SAFE

    def test_string_equality(self) -> None:
        assert Intrusiveness.PASSIVE == "passive"
        assert Intrusiveness.DISRUPTIVE == "disruptive"
        assert Intrusiveness("active-safe") == Intrusiveness.ACTIVE_SAFE

    def test_hashable(self) -> None:
        s = {Intrusiveness.PASSIVE, Intrusiveness.ACTIVE_SAFE}
        assert Intrusiveness.PASSIVE in s


@pytest.mark.unit
class TestTaskStateMachine:
    def test_legal_transitions(self) -> None:
        # PENDING transitions
        assert can_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        assert can_transition(TaskStatus.PENDING, TaskStatus.BLOCKED)
        assert can_transition(TaskStatus.PENDING, TaskStatus.CANCELLED)
        assert can_transition(TaskStatus.PENDING, TaskStatus.SKIPPED)

        # RUNNING transitions
        assert can_transition(TaskStatus.RUNNING, TaskStatus.SUCCEEDED)
        assert can_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        assert can_transition(TaskStatus.RUNNING, TaskStatus.CANCELLED)

        # Self transition is idempotent
        assert can_transition(TaskStatus.RUNNING, TaskStatus.RUNNING)

    def test_illegal_transitions_raise(self) -> None:
        # Terminal states have no transitions
        for terminal in (
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.SKIPPED,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        ):
            assert not can_transition(terminal, TaskStatus.RUNNING)
            with pytest.raises(ValidationFailure):
                assert_transition(terminal, TaskStatus.RUNNING)

        # Cannot jump pending -> succeeded directly
        assert not can_transition(TaskStatus.PENDING, TaskStatus.SUCCEEDED)
        with pytest.raises(ValidationFailure):
            assert_transition(TaskStatus.PENDING, TaskStatus.SUCCEEDED)


@pytest.mark.unit
class TestClockAndIdGenerators:
    def test_utc_clock_is_timezone_aware(self) -> None:
        clock = UtcClock()
        now = clock.now()
        assert now.tzinfo is not None
        assert now.tzinfo == UTC

    def test_frozen_clock_advance(self) -> None:
        t0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
        clock = FrozenClock(t0)
        assert clock.now() == t0
        clock.advance(3600)
        assert clock.now().hour == 11

    def test_uuid_generator(self) -> None:
        gen = UuidGenerator()
        id1 = gen.generate()
        id2 = gen.generate()
        assert len(id1) == 36
        assert id1 != id2

    def test_static_id_generator(self) -> None:
        gen = StaticIdGenerator(ids=["custom-1", "custom-2"])
        assert gen.generate() == "custom-1"
        assert gen.generate() == "custom-2"
        assert gen.generate() == "id-0001"
