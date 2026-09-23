"""Geometric Brownian Motion market data simulator."""

import asyncio
import math
import random

import numpy as np

from app.market.cache import price_cache
from app.market.interface import MarketDataProvider

# Seed prices and per-ticker parameters (annual drift, annual volatility)
TICKER_CONFIG = {
    "AAPL": {"seed": 190.0, "drift": 0.08, "vol": 0.25},
    "GOOGL": {"seed": 175.0, "drift": 0.10, "vol": 0.28},
    "MSFT": {"seed": 420.0, "drift": 0.09, "vol": 0.24},
    "AMZN": {"seed": 185.0, "drift": 0.12, "vol": 0.30},
    "TSLA": {"seed": 250.0, "drift": 0.05, "vol": 0.50},
    "NVDA": {"seed": 880.0, "drift": 0.15, "vol": 0.40},
    "META": {"seed": 500.0, "drift": 0.10, "vol": 0.32},
    "JPM": {"seed": 195.0, "drift": 0.06, "vol": 0.20},
    "V": {"seed": 280.0, "drift": 0.07, "vol": 0.18},
    "NFLX": {"seed": 630.0, "drift": 0.11, "vol": 0.35},
}

# Correlation matrix sectors: tech stocks correlated, finance separate
TECH_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]
FINANCE_TICKERS = ["JPM", "V"]

# Parameters for tickers without an explicit config (seed price is randomized)
UNKNOWN_DRIFT = 0.08
UNKNOWN_VOL = 0.30
UNKNOWN_SEED_RANGE = (50.0, 300.0)

UPDATE_INTERVAL = 0.5  # seconds
EVENT_PROBABILITY = 0.005  # per ticker per update
EVENT_MIN_PCT = 0.02
EVENT_MAX_PCT = 0.05


def _build_correlation_matrix(tickers: list[str]) -> np.ndarray:
    """Build a correlation matrix with tech and finance clusters."""
    n = len(tickers)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = tickers[i], tickers[j]
            if ti in TECH_TICKERS and tj in TECH_TICKERS:
                corr[i, j] = corr[j, i] = 0.6
            elif ti in FINANCE_TICKERS and tj in FINANCE_TICKERS:
                corr[i, j] = corr[j, i] = 0.5
            else:
                corr[i, j] = corr[j, i] = 0.2
    return corr


def _ticker_config(ticker: str) -> dict:
    """Return GBM parameters for a ticker, generating them for unknown tickers."""
    if ticker in TICKER_CONFIG:
        return TICKER_CONFIG[ticker]
    seed = round(random.uniform(*UNKNOWN_SEED_RANGE), 2)
    return {"seed": seed, "drift": UNKNOWN_DRIFT, "vol": UNKNOWN_VOL}


class Simulator(MarketDataProvider):
    """GBM-based market data simulator."""

    def __init__(self, tickers: list[str] | None = None):
        self._task: asyncio.Task | None = None
        self._dt = UPDATE_INTERVAL / (252 * 6.5 * 3600)  # fraction of trading year
        self._tickers: list[str] = []
        self._config: dict[str, dict] = {}
        self._prices: dict[str, float] = {}
        for ticker in tickers or TICKER_CONFIG:
            self._register(ticker)
        self._rebuild_cholesky()

    def _register(self, ticker: str) -> None:
        """Track a ticker with its GBM parameters and seed price."""
        cfg = _ticker_config(ticker)
        self._tickers.append(ticker)
        self._config[ticker] = cfg
        self._prices[ticker] = cfg["seed"]

    def _rebuild_cholesky(self) -> None:
        """Precompute Cholesky decomposition for correlated random draws."""
        corr = _build_correlation_matrix(self._tickers)
        self._cholesky = np.linalg.cholesky(corr)

    def add_ticker(self, ticker: str) -> None:
        """Start simulating a ticker and seed its price into the cache."""
        if ticker in self._config:
            return
        self._register(ticker)
        self._rebuild_cholesky()
        price_cache.update(ticker, self._prices[ticker])

    async def start(self) -> None:
        """Start the simulation loop."""
        # Seed initial prices into cache
        for ticker, price in self._prices.items():
            price_cache.update(ticker, price)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the simulation loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main simulation loop."""
        while True:
            self._step()
            await asyncio.sleep(UPDATE_INTERVAL)

    def _step(self) -> None:
        """Advance all prices by one GBM step with correlation."""
        n = len(self._tickers)
        # Correlated normal draws
        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent

        for i, ticker in enumerate(self._tickers):
            cfg = self._config[ticker]
            drift = cfg["drift"]
            vol = cfg["vol"]
            s = self._prices[ticker]

            # GBM: dS = S * (mu*dt + sigma*sqrt(dt)*Z)
            ds = s * (drift * self._dt + vol * math.sqrt(self._dt) * z_correlated[i])
            new_price = s + ds

            # Random event: sudden 2-5% move
            if random.random() < EVENT_PROBABILITY:
                pct = random.uniform(EVENT_MIN_PCT, EVENT_MAX_PCT)
                sign = random.choice([-1, 1])
                new_price *= 1 + sign * pct

            new_price = max(new_price, 0.01)  # floor at 1 cent
            self._prices[ticker] = new_price
            price_cache.update(ticker, new_price)
