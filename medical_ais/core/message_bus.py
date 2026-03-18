"""
In-process async event bus for inter-component communication.
Decouples components so they don't reference each other directly.
Pattern: publish-subscribe with typed event payloads.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Type alias: async handler that receives an event payload dict
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class Event:
    """A typed, immutable event published onto the bus."""

    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"


class MessageBus:
    """
    Lightweight async publish-subscribe bus.

    Usage
    -----
    bus = MessageBus()
    bus.subscribe("patient.alert", my_handler)
    await bus.publish(Event("patient.alert", {"patient_id": "123"}, source="triage_node"))
    """

    def __init__(self) -> None:
        # topic → list of handlers
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register *handler* to be called whenever *topic* is published."""
        self._handlers[topic].append(handler)
        logger.debug("message_bus.subscribe", topic=topic, handler=handler.__qualname__)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Remove *handler* from *topic*. No-op if not registered."""
        try:
            self._handlers[topic].remove(handler)
        except ValueError:
            pass

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        """
        Deliver *event* to all subscribed handlers concurrently.
        Handler errors are logged but never propagate to the publisher.
        """
        handlers = list(self._handlers.get(event.topic, []))
        if not handlers:
            logger.debug("message_bus.no_handlers", topic=event.topic)
            return

        logger.debug(
            "message_bus.publish",
            topic=event.topic,
            source=event.source,
            handler_count=len(handlers),
        )

        results = await asyncio.gather(
            *(h(event.payload) for h in handlers),
            return_exceptions=True,
        )

        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "message_bus.handler_error",
                    topic=event.topic,
                    handler=handler.__qualname__,
                    error=str(result),
                )

    # ── Convenience ───────────────────────────────────────────────────────────

    def topics(self) -> list[str]:
        """Return all topics that have at least one subscriber."""
        return [t for t, h in self._handlers.items() if h]


# Module-level singleton — import and use directly
_bus: MessageBus | None = None


def get_bus() -> MessageBus:
    """Return the module-level MessageBus singleton (lazy init)."""
    global _bus  # noqa: PLW0603
    if _bus is None:
        _bus = MessageBus()
    return _bus
