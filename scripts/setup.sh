#!/usr/bin/env bash
# mneme — local environment setup (run on HOME machine, not the company one).
#
# Idempotent: safe to re-run.
# Steps:
#   1. Install PostgreSQL 17 + pgvector via Homebrew
#   2. Create `mneme` database + pgvector extension
#   3. Apply schema
#   4. Install uv (if missing) and sync Python deps
#   5. Verify .env presence
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "===> mneme setup starting in $PROJECT_ROOT"

PG_FORMULA="postgresql@17"
PG_BIN="/opt/homebrew/opt/${PG_FORMULA}/bin"

# ----- 1. Homebrew -----
if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not found. Install from https://brew.sh and re-run."
    exit 1
fi

# ----- 2. PostgreSQL + pgvector -----
echo "===> installing ${PG_FORMULA} + pgvector..."
brew list "${PG_FORMULA}" >/dev/null 2>&1 || brew install "${PG_FORMULA}"
brew list pgvector     >/dev/null 2>&1 || brew install pgvector
brew services stop postgresql@16 >/dev/null 2>&1 || true
brew services start "${PG_FORMULA}" || true   # may already be running

# Wait for PG up (brew services start is async)
for i in {1..10}; do
    "${PG_BIN}/pg_isready" >/dev/null 2>&1 && break
    echo "    waiting for postgres ($i/10)..."
    sleep 1
done

# ----- 3. Create database + schema -----
echo "===> creating mneme database..."
"${PG_BIN}/createdb" mneme 2>/dev/null || echo "    mneme db already exists"
"${PG_BIN}/psql" mneme -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null

echo "===> applying schema..."
"${PG_BIN}/psql" mneme -f src/mneme/db/schema.sql >/dev/null
echo "    schema applied."

# ----- 3b. Runtime directories -----
mkdir -p logs

# ----- 4. uv + Python deps -----
if ! command -v uv >/dev/null 2>&1; then
    echo "===> installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi

echo "===> syncing Python dependencies..."
uv sync

# ----- 5. .env check -----
if [[ ! -f .env ]]; then
    cp .env.example .env
    echo
    echo "===> .env was missing — copied from .env.example."
    echo "     Now edit .env and fill:"
    echo "       - DEEPSEEK_API_KEY (you have credit)"
    echo "       - EMBED_API_KEY    (DashScope text-embedding-v3)"
    echo "       - DATABASE_URL     (set the password matching your local PG role)"
    echo
    echo "     Then run:   uv run python -m mneme"
    exit 0
fi

echo
echo "===> setup complete. Start mneme with:"
echo "       uv run python -m mneme"
