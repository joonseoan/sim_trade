"""Environment-driven market data provider selection and ticker registration."""

import os

from app.market.interface import MarketDataProvider

_active: MarketDataProvider | None = None


def create_provider(tickers: list[str]) -> MarketDataProvider:
    """Create the provider for the environment and make it the active one."""
    global _active
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        from app.market.massive import MassiveClient

        _active = MassiveClient(tickers=tickers)
    else:
        from app.market.simulator import Simulator

        _active = Simulator(tickers=tickers)
    return _active


def register_ticker(ticker: str) -> None:
    """Ask the active provider to start producing prices for a ticker."""
    if _active:
        _active.add_ticker(ticker)
