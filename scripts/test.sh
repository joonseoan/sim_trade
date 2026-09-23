#!/usr/bin/env bash
# Run backend (pytest) and frontend (vitest) unit tests. Exits non-zero on the first failure.
# Used as the refinery test_command, so it installs frontend deps when missing.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

cd "$root/backend"
uv run pytest -q

cd "$root/frontend"
[ -d node_modules ] || npm ci --no-audit --no-fund
npm test
