# FinAlly Plan

Agent-facing summary of the architecture and build status. [SPEC.md](../SPEC.md) is the source of truth for requirements; this file maps the spec onto the code that exists today. Live task status is in beads (`bd children st-quk`).

## Architecture

One container, one port (8000). FastAPI serves the REST API, the SSE price stream, and the static Next.js export.

```
browser ──/api/*──────────► FastAPI routers ──► SQLite (DB_PATH, default db/finally.db)
        ◄─/api/stream/*─── SSE ◄── price_cache ◄── Simulator | MassiveClient
        ──/*──────────────► StaticFiles (static/ = frontend/out)
```

### Backend (`backend/`, uv project)

| Module | Role |
|---|---|
| `app/main.py` | App entry. Lifespan: `init_db()`, start market provider, start snapshot recorder. Mounts `static/` if present. `GET /api/health` |
| `app/database.py` | Schema SQL, default seed (10 tickers, $10,000 cash), `get_db()`, lazy `init_db()` |
| `app/market/interface.py` | `MarketDataProvider` ABC |
| `app/market/provider.py` | `create_provider()` picks `MassiveClient` if `MASSIVE_API_KEY` is set, else `Simulator`. `register_ticker()` adds a ticker to the active provider |
| `app/market/simulator.py` | Correlated GBM, 500 ms ticks, random 2-5% events |
| `app/market/massive.py` | Polygon.io REST poller (15 s default for the free tier) |
| `app/market/cache.py` | `price_cache`: the single in-memory latest-price store every consumer reads |
| `app/market/stream.py` | `GET /api/stream/prices` (SSE) |
| `app/portfolio.py` | `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history`, `take_snapshot()` |
| `app/snapshots.py` | Background task that records a portfolio snapshot every 30 s |
| `app/watchlist.py` | `GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}` |
| `app/chat.py` | `POST /api/chat`: LiteLLM `acompletion` with structured output, auto-executes trades and watchlist changes. `LLM_MOCK=true` returns deterministic responses |
| `app/prices.py` | Unused duplicate cache, pending removal (st-quk.12). Do not import it |

### Frontend (`frontend/`, Next.js static export)

- `src/app/page.tsx`: single-page workstation layout that polls the portfolio every 15 s.
- `src/hooks/useMarketData.ts`: `EventSource` client for the SSE stream.
- `src/lib/api.ts`: typed REST client.
- `src/components/`: Header, Watchlist (with Sparkline), MainChart, PortfolioHeatmap, PnlChart, PositionsTable, TradeBar, ChatPanel.
- `next.config.ts`: `output: "export"`, with dev-only rewrites that proxy `/api` to the backend on port 8000.

### Tests

- `backend/tests/`: pytest (`cd backend && uv run pytest`). Lint and types: `scripts/check_backend.sh`.
- `frontend/src/__tests__/`: Vitest (`cd frontend && npm test`).
- `test/`: Playwright E2E, run through `docker-compose.test.yml` with `LLM_MOCK=true`.

### Deployment

The multi-stage `Dockerfile` builds the frontend with Node 20, then copies `out/` into `static/` in a Python 3.12 image and runs uvicorn from `/app/backend`. `scripts/start_*`/`stop_*` wrap `docker run` and mount the `finally-data` volume at `/app/db`.

## Deviations from SPEC

- The spec puts schema and seed logic in `backend/db/`. It lives in `app/database.py` instead.

## Build status (2026-09-23)

Every SPEC feature area is implemented: market data (simulator and Massive), SSE, portfolio and trading, watchlist, P&L snapshots, LLM chat with auto-execution, the frontend workstation, Docker, and the start/stop scripts. Backend and frontend unit tests pass.

Open work under epic `st-quk`:

| Bead | Priority | Summary |
|---|---|---|
| st-quk.14 | P1 | Docker writes the DB to `/app/backend/db`, not the `/app/db` volume, so data is lost when the container is removed |
| st-quk.7 | P2 | Add tests for the SSE stream, provider selection, and chat trade pricing |
| st-quk.16 | P2 | Wire the refinery `test_command` so merges are verified automatically |
| st-quk.11 | P3 | Chat trades skip the post-trade portfolio snapshot |
| st-quk.12 | P3 | Remove `app/prices.py` (MR in queue) |
