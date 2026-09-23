"""Tests for registering new watchlist tickers with the market data provider."""

import pytest

from app.database import DEFAULT_TICKERS
from app.market import provider
from app.market.cache import price_cache
from app.market.massive import MassiveClient
from app.market.simulator import Simulator


@pytest.fixture
def isolated_market(monkeypatch):
    """Start with an empty price cache and no active provider."""
    monkeypatch.setattr(price_cache, "_prices", {})
    monkeypatch.setattr(provider, "_active", None)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)


def test_simulator_accepts_custom_tickers():
    sim = Simulator(tickers=["AAPL", "PYPL"])
    assert set(sim._prices) == {"AAPL", "PYPL"}
    assert sim._cholesky.shape == (2, 2)


def test_simulator_add_ticker_seeds_cache_and_steps(isolated_market):
    sim = Simulator()
    sim.add_ticker("PYPL")
    assert price_cache.get("PYPL") is not None
    assert sim._cholesky.shape == (11, 11)
    before = sim._prices["PYPL"]
    sim._step()
    assert sim._prices["PYPL"] != before


def test_simulator_add_existing_ticker_is_noop():
    sim = Simulator()
    sim.add_ticker("AAPL")
    assert sim._tickers.count("AAPL") == 1


def test_massive_add_ticker(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    client = MassiveClient(tickers=DEFAULT_TICKERS)
    client.add_ticker("PYPL")
    client.add_ticker("PYPL")
    assert client._tickers.count("PYPL") == 1
    assert "PYPL" not in DEFAULT_TICKERS


def test_create_provider_uses_given_tickers(isolated_market):
    sim = provider.create_provider(["AAPL", "PYPL"])
    assert isinstance(sim, Simulator)
    assert set(sim._prices) == {"AAPL", "PYPL"}


async def test_watchlist_add_registers_ticker(client, isolated_market):
    sim = provider.create_provider(DEFAULT_TICKERS)
    assert isinstance(sim, Simulator)
    resp = await client.post("/api/watchlist", json={"ticker": "pypl"})
    assert resp.status_code == 200
    assert resp.json()["price"] is not None
    assert "PYPL" in sim._prices


async def test_chat_watchlist_add_registers_ticker(
    client, isolated_market, monkeypatch
):
    monkeypatch.setenv("LLM_MOCK", "true")
    provider.create_provider(DEFAULT_TICKERS)
    resp = await client.post("/api/chat", json={"message": "add PYPL to watchlist"})
    assert resp.status_code == 200
    assert price_cache.get("PYPL") is not None
