"""Unit tests for the event bus, subscriber isolation, and event sanitization."""

from __future__ import annotations

import asyncio

import pytest

from nayraastra.core.events.bus import EventBus, RecordingSubscriber
from nayraastra.core.events.models import (
    EngagementOpened,
    TaskBlocked,
    TaskOutput,
    TaskQueued,
)


@pytest.mark.unit
class TestEventSanitization:
    def test_control_characters_stripped_from_task_output(self) -> None:
        raw_line = "\x1b[31;1mCRITICAL WARNING\x1b[0m\x07\x08"
        event = TaskOutput(
            task_id="t1",
            engagement_id="eng1",
            line=raw_line,
        )
        assert event.line == "CRITICAL WARNING"
        assert "\x1b" not in event.line
        assert "\x07" not in event.line

    def test_reason_sanitized_in_task_blocked(self) -> None:
        event = TaskBlocked(
            task_id="t2",
            engagement_id="eng1",
            reason="Blocked by \x1b[32mPolicy\x1b[0m",
        )
        assert event.reason == "Blocked by Policy"


@pytest.mark.unit
class TestEventBus:
    def test_ordering_and_wildcard(self) -> None:
        bus = EventBus()
        rec = RecordingSubscriber(bus, "*")

        bus.publish(EngagementOpened(engagement_id="e1"))
        bus.publish(
            TaskQueued(
                task_id="t1",
                engagement_id="e1",
                module_name="port_scan",
                adapter_name="fake",
                target="10.0.0.1",
            )
        )

        assert len(rec.events) == 2
        assert isinstance(rec.events[0], EngagementOpened)
        assert isinstance(rec.events[1], TaskQueued)

    def test_failing_subscriber_isolated(self) -> None:
        bus = EventBus()
        rec = RecordingSubscriber(bus, "*")

        def _bad_subscriber(event: object) -> None:
            raise RuntimeError("Subscriber explosion!")

        bus.subscribe("*", _bad_subscriber)

        # Publisher must not raise even if subscriber crashes
        bus.publish(EngagementOpened(engagement_id="e-safe"))
        assert len(rec.events) == 1

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[str] = []

        sub = bus.subscribe(EngagementOpened, lambda ev: received.append(ev.engagement_id))
        bus.publish(EngagementOpened(engagement_id="e1"))
        assert received == ["e1"]

        sub.unsubscribe()
        bus.publish(EngagementOpened(engagement_id="e2"))
        assert received == ["e1"]

    def test_async_subscriber(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            async_received: list[str] = []

            async def _async_handler(ev: EngagementOpened) -> None:
                await asyncio.sleep(0.01)
                async_received.append(ev.engagement_id)

            bus.subscribe(EngagementOpened, _async_handler)
            await bus.publish_async(EngagementOpened(engagement_id="async-e1"))
            assert async_received == ["async-e1"]

        asyncio.run(_run())
