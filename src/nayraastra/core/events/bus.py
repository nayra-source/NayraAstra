"""In-process asynchronous/synchronous event bus."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable
from typing import Any

from nayraastra.core.events.models import BaseEvent

logger = logging.getLogger("nayraastra.events")


class Subscription:
    """Handle for an active event subscription."""

    def __init__(
        self,
        event_pattern: str,
        handler: Callable[[Any], Any],
        bus: EventBus,
    ) -> None:
        self.event_pattern = event_pattern
        self.handler = handler
        self._bus = bus
        self._active = True

    def unsubscribe(self) -> None:
        """Cancel this subscription."""
        if self._active:
            self._bus.unsubscribe(self)
            self._active = False


class EventBus:
    """In-process pub/sub event bus supporting sync and async subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], Any]]] = {}

    def subscribe(
        self,
        event_type: type[BaseEvent] | str,
        handler: Callable[[Any], Any],
    ) -> Subscription:
        """Register a handler for a specific event type or wildcard '*'."""
        if isinstance(event_type, type) and issubclass(event_type, BaseEvent):
            if "type" in event_type.model_fields:
                field = event_type.model_fields["type"]
                pattern = str(field.default) if field.default is not None else event_type.__name__
            else:
                pattern = event_type.__name__
        else:
            pattern = str(event_type)

        if pattern not in self._subscribers:
            self._subscribers[pattern] = []
        self._subscribers[pattern].append(handler)
        return Subscription(pattern, handler, self)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscriber."""
        pattern = subscription.event_pattern
        if pattern in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[pattern].remove(subscription.handler)
            if not self._subscribers[pattern]:
                del self._subscribers[pattern]

    def _get_handlers(self, event_type_str: str) -> list[Callable[[Any], Any]]:
        handlers = list(self._subscribers.get(event_type_str, []))
        if "*" in self._subscribers:
            handlers.extend(self._subscribers["*"])
        return handlers

    def publish(self, event: BaseEvent) -> None:
        """Publish an event to all matching subscribers.

        Subscriber failures are isolated and never break the publisher.
        """
        event_type_str = getattr(event, "type", type(event).__name__)
        handlers = self._get_handlers(event_type_str)

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._safe_async_call(handler, event))
                    except RuntimeError:
                        asyncio.run(self._safe_async_call(handler, event))
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Event subscriber error in %r for event %r: %s",
                    handler,
                    event_type_str,
                    exc,
                )

    async def publish_async(self, event: BaseEvent) -> None:
        """Asynchronously publish an event, awaiting async handlers."""
        event_type_str = getattr(event, "type", type(event).__name__)
        handlers = self._get_handlers(event_type_str)

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Event subscriber error in %r for event %r: %s",
                    handler,
                    event_type_str,
                    exc,
                )

    async def _safe_async_call(self, handler: Callable[[Any], Any], event: BaseEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Async event subscriber error in %r for event %r: %s",
                handler,
                getattr(event, "type", type(event).__name__),
                exc,
            )


class RecordingSubscriber:
    """Test helper that records all events published to the bus."""

    def __init__(self, bus: EventBus, event_type: type[BaseEvent] | str = "*") -> None:
        self.events: list[BaseEvent] = []
        self._subscription = bus.subscribe(event_type, self._record)

    def _record(self, event: BaseEvent) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()

    def unsubscribe(self) -> None:
        self._subscription.unsubscribe()
