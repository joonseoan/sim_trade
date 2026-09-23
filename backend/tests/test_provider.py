"""Tests for environment-driven market data provider selection."""

import pytest

from app.market import provider
from app.market.massive import MassiveClient
from app.market.simulator import Simulator


@pytest.fixture(autouse=True)
def no_active_provider(monkeypatch):
    """Start each test with no active provider and no Massive key."""
    monkeypatch.setattr(provider, "_active", None)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)


def test_no_key_selects_simulator():
    assert isinstance(provider.create_provider(["AAPL"]), Simulator)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_key_selects_simulator(monkeypatch, value):
    monkeypatch.setenv("MASSIVE_API_KEY", value)
    assert isinstance(provider.create_provider(["AAPL"]), Simulator)


def test_key_selects_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    client = provider.create_provider(["AAPL", "MSFT"])
    assert isinstance(client, MassiveClient)
    assert client._tickers == ["AAPL", "MSFT"]


def test_created_provider_becomes_active(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    client = provider.create_provider(["AAPL"])
    assert provider._active is client


def test_register_ticker_delegates_to_active(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    client = provider.create_provider(["AAPL"])
    assert isinstance(client, MassiveClient)
    provider.register_ticker("PYPL")
    assert client._tickers == ["AAPL", "PYPL"]


def test_register_ticker_without_provider_is_noop():
    provider.register_ticker("PYPL")
    assert provider._active is None
