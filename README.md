# FinAlly

FinAlly (Finance Ally) is an AI-powered trading workstation. It streams live market prices, lets you trade a simulated $10,000 portfolio, and includes an LLM chat assistant that can analyze positions, execute trades, and manage your watchlist.

- **Backend**: FastAPI (Python, `uv`), SQLite, Server-Sent Events for prices
- **Frontend**: Next.js static export, served by FastAPI
- **AI**: LiteLLM via OpenRouter
- **Market data**: built-in simulator by default, or Massive (Polygon.io) with an API key

Everything runs in one container on port 8000. See [SPEC.md](SPEC.md) for the full design.

## Configuration

Copy the example file and fill in your key:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter key for the chat assistant |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data. If empty, the simulator is used |
| `LLM_MOCK` | No | `true` returns deterministic mock chat responses (no API calls). Default `false` |

## Run with Docker

```bash
./scripts/start_mac.sh           # build (first time) and run, then open http://localhost:8000
./scripts/start_mac.sh --build   # force a rebuild
./scripts/stop_mac.sh            # stop the container
```

The script builds the `finally` image, runs it with `--env-file .env`, and mounts the `finally-data` volume at `/app/db`. It also works on Linux. On Windows, use `scripts/start_windows.ps1` and `scripts/stop_windows.ps1`.

You can also run it with `docker compose up --build`.

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Node.js 20+.

Backend (API on http://localhost:8000):

```bash
cd backend
uv sync
uv run --env-file ../.env uvicorn app.main:app --reload --port 8000
```

Frontend (dev server on http://localhost:3000, proxies `/api` to the backend):

```bash
cd frontend
npm ci
npm run dev
```

To serve the built UI from the backend instead, run `npm run build` in `frontend/` and copy `frontend/out/` to `static/` at the repo root.

The local SQLite database is created at `backend/db/finally.db`. Override it with `DB_PATH`. In Docker it defaults to `/app/db/finally.db` (the volume mount).

## Tests

```bash
./scripts/test.sh                  # backend + frontend unit tests (refinery test_command)
cd backend && uv run pytest        # backend unit tests
cd frontend && npm test            # frontend unit tests (Vitest)
cd frontend && npm run lint        # frontend lint
./scripts/check_backend.sh         # backend lint, format and type checks (ruff, pyright)
```

End-to-end tests (Playwright) run against the app in Docker with `LLM_MOCK=true`:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```
