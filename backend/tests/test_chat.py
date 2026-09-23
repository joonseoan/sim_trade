"""Tests for the POST /api/chat endpoint in mock mode."""

import os

os.environ["LLM_MOCK"] = "true"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.market.cache import price_cache


@pytest.fixture(autouse=True)
def seed_prices():
    """Seed the live price cache so chat trades have a market price."""
    price_cache.update("AAPL", 150.0)
    price_cache.update("TSLA", 150.0)
    yield
    price_cache._prices.clear()


@pytest_asyncio.fixture
async def client(tmp_path):
    """Async test client with a fresh per-test SQLite DB."""
    import app.database as database

    db_file = str(tmp_path / "test.db")
    database.DB_PATH = db_file
    await database.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_chat_greeting(client):
    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "FinAlly" in data["message"]
    assert data["trades"] is None
    assert data["watchlist_changes"] is None


async def test_chat_buy_aapl(client):
    """Mock buy always buys 10 shares of the matched ticker at the cached price."""
    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] is not None
    assert len(data["trades"]) == 1
    trade = data["trades"][0]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 10
    # No errors appended
    assert "Errors" not in data["message"]


async def test_chat_sell_insufficient(client):
    """Selling without owning shares should report error in message."""
    resp = await client.post("/api/chat", json={"message": "sell some AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    # Upstream appends errors to message
    assert "Insufficient" in data["message"] or "Errors" in data["message"]


async def test_chat_buy_then_sell(client):
    """Buy then sell should succeed."""
    # Buy first (10 shares at $150 = $1500)
    resp = await client.post("/api/chat", json={"message": "buy some TSLA"})
    data = resp.json()
    assert data["trades"][0]["ticker"] == "TSLA"
    assert "Errors" not in data["message"]

    # Sell (10 shares at the cached price)
    resp = await client.post("/api/chat", json={"message": "sell some TSLA"})
    data = resp.json()
    assert "Insufficient" not in data["message"]


async def test_chat_buy_insufficient_cash(client):
    """Buying more than cash allows should fail. 10 * $150 = $1500, so
    need to exhaust cash first."""
    # Buy 7 times: 7 * 10 * $150 = $10,500 > $10,000
    # First 6 buys: 6 * $1500 = $9000 (leaving $1000)
    for _ in range(6):
        await client.post("/api/chat", json={"message": "buy some AAPL"})

    # 7th buy: $1500 > $1000 remaining
    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    data = resp.json()
    assert "Insufficient" in data["message"]


async def test_chat_watchlist_add(client):
    resp = await client.post("/api/chat", json={"message": "add PYPL to watchlist"})
    data = resp.json()
    assert data["watchlist_changes"] is not None
    assert data["watchlist_changes"][0]["ticker"] == "PYPL"
    assert data["watchlist_changes"][0]["action"] == "add"


async def test_chat_watchlist_remove(client):
    resp = await client.post("/api/chat", json={"message": "remove NFLX"})
    data = resp.json()
    assert data["watchlist_changes"] is not None
    assert data["watchlist_changes"][0]["ticker"] == "NFLX"
    assert data["watchlist_changes"][0]["action"] == "remove"


async def test_chat_portfolio_query(client):
    resp = await client.post("/api/chat", json={"message": "show my portfolio"})
    data = resp.json()
    assert "portfolio" in data["message"].lower()
    assert data["trades"] is None


async def test_chat_fallback(client):
    resp = await client.post("/api/chat", json={"message": "random nonsense xyz"})
    data = resp.json()
    assert "trade" in data["message"].lower() or "portfolio" in data["message"].lower()


async def _recorded_trades() -> list[tuple[str, str, float]]:
    """Return (ticker, side, price) for every trade in the test DB."""
    import app.database as database

    db = await database.get_db()
    try:
        cur = await db.execute(
            "SELECT ticker, side, price FROM trades ORDER BY executed_at"
        )
        return [(r["ticker"], r["side"], r["price"]) for r in await cur.fetchall()]
    finally:
        await db.close()


async def test_chat_buy_executes_at_cached_price(client):
    price_cache.update("AAPL", 187.25)
    await client.post("/api/chat", json={"message": "buy some AAPL"})

    assert await _recorded_trades() == [("AAPL", "buy", 187.25)]
    portfolio = (await client.get("/api/portfolio")).json()
    assert portfolio["cash_balance"] == 10000.0 - 10 * 187.25
    assert portfolio["positions"][0]["avg_cost"] == 187.25


async def test_chat_sell_executes_at_latest_cached_price(client):
    price_cache.update("AAPL", 187.25)
    await client.post("/api/chat", json={"message": "buy some AAPL"})
    price_cache.update("AAPL", 200.0)
    await client.post("/api/chat", json={"message": "sell some AAPL"})

    assert await _recorded_trades() == [
        ("AAPL", "buy", 187.25),
        ("AAPL", "sell", 200.0),
    ]
    portfolio = (await client.get("/api/portfolio")).json()
    assert portfolio["cash_balance"] == 10000.0 - 10 * 187.25 + 10 * 200.0


async def test_chat_and_manual_trade_use_same_price(client):
    price_cache.update("AAPL", 187.25)
    await client.post("/api/chat", json={"message": "buy some AAPL"})
    await client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 10, "side": "buy"},
    )

    prices = [price for _, _, price in await _recorded_trades()]
    assert prices == [187.25, 187.25]


async def test_chat_trade_without_cached_price_fails(client):
    resp = await client.post("/api/chat", json={"message": "buy some MSFT"})

    assert "No price available for MSFT" in resp.json()["message"]
    assert await _recorded_trades() == []


async def test_chat_trade_creates_snapshot(client):
    """A chat-executed trade records a post-trade portfolio snapshot."""
    await client.post("/api/chat", json={"message": "buy some AAPL"})
    resp = await client.get("/api/portfolio/history")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
