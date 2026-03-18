"""Unit tests for the message bus."""
from __future__ import annotations

import pytest

from medical_ais.core.message_bus import Event, MessageBus


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = MessageBus()
    received = []

    async def handler(payload: dict):
        received.append(payload)

    bus.subscribe("test.event", handler)
    await bus.publish(Event("test.event", {"data": 42}))

    assert len(received) == 1
    assert received[0]["data"] == 42


@pytest.mark.asyncio
async def test_no_handlers_no_error():
    bus = MessageBus()
    await bus.publish(Event("unknown.event", {}))  # Should not raise


@pytest.mark.asyncio
async def test_handler_error_does_not_propagate():
    bus = MessageBus()

    async def bad_handler(payload):
        raise ValueError("handler crashed")

    bus.subscribe("error.event", bad_handler)
    await bus.publish(Event("error.event", {}))  # Should not raise


@pytest.mark.asyncio
async def test_multiple_handlers():
    bus = MessageBus()
    results = []

    for i in range(3):
        async def make_handler(i=i):
            async def h(payload):
                results.append(i)
            return h
        bus.subscribe("multi", await make_handler())

    await bus.publish(Event("multi", {}))
    assert sorted(results) == [0, 1, 2]


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = MessageBus()
    received = []

    async def handler(payload):
        received.append(payload)

    bus.subscribe("evt", handler)
    bus.unsubscribe("evt", handler)
    await bus.publish(Event("evt", {}))
    assert len(received) == 0
