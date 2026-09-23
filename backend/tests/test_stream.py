"""Tests for the SSE price stream: event shape, cadence, and endpoint."""

import json

import pytest
from sse_starlette.sse import EventSourceResponse

from app.market import stream
from app.market.cache import price_cache


@pytest.fixture
def sleeps(monkeypatch):
    """Empty the price cache and record stream sleeps instead of waiting."""
    monkeypatch.setattr(price_cache, "_prices", {})
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(stream.asyncio, "sleep", fake_sleep)
    return delays


async def test_event_shape_matches_cached_price(sleeps):
    cached = price_cache.update("AAPL", 190.5)
    event = await anext(stream._price_event_generator())
    assert event["event"] == "price"
    data = json.loads(event["data"])
    assert data == cached.model_dump()
    assert set(data) == {
        "ticker",
        "price",
        "previous_price",
        "timestamp",
        "direction",
    }


async def test_one_event_per_ticker_then_half_second_sleep(sleeps):
    price_cache.update("AAPL", 190.0)
    price_cache.update("MSFT", 420.0)
    gen = stream._price_event_generator()

    first_cycle = [json.loads((await anext(gen))["data"])["ticker"] for _ in range(2)]
    assert first_cycle == ["AAPL", "MSFT"]
    assert sleeps == []

    await anext(gen)
    assert sleeps == [0.5]


async def test_empty_cache_emits_nothing_until_prices_arrive(sleeps, monkeypatch):
    async def seed_on_sleep(delay: float) -> None:
        sleeps.append(delay)
        price_cache.update("TSLA", 250.0)

    monkeypatch.setattr(stream.asyncio, "sleep", seed_on_sleep)
    event = await anext(stream._price_event_generator())
    assert sleeps == [0.5]
    assert json.loads(event["data"])["ticker"] == "TSLA"


async def test_endpoint_returns_event_source_response():
    resp = await stream.stream_prices()
    assert isinstance(resp, EventSourceResponse)
    assert resp.media_type == "text/event-stream"
