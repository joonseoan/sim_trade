#!/usr/bin/env bash
# Lint, format-check, and type-check the backend. Exits non-zero on the first failure.
set -euo pipefail

cd "$(dirname "$0")/../backend"

uv run ruff check .
uv run ruff format --check .
uv run pyright
