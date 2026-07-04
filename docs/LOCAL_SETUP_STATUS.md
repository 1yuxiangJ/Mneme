# Local Setup Status

> Updated on 2026-07-05 by Codex.

## 2026-07-05 Update

Current quality gate:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```

Observed result:

```text
ruff: All checks passed
mypy: Success, no issues found in 24 source files
pytest: 28 passed, 1 warning
```

Real MCP + Sleep smoke has also been verified:

```bash
scripts/claude-mneme.sh mcp list
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10
```

## 2026-07-01 Update

Core local verification now passes:

```bash
/Users/mac/.local/bin/uv run pytest
/Users/mac/.local/bin/uv run pytest --run-integration
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run python -c "from mneme.awake.agent import get_awake_agent; get_awake_agent(); from mneme.sleep.agent import get_sleep_graph; get_sleep_graph(); print('agents ok')"
```

Previous mypy strict annotation debt has been fixed.

> Updated on 2026-06-18 by Codex.

## What Was Verified

Claude Code is installed:

```bash
claude --version
# 2.1.179 (Claude Code)
```

Project-scoped MCP config is present:

```text
/Users/mac/dream/.mcp.json
```

Claude Code recognizes the server:

```bash
cd /Users/mac/dream
claude mcp list
```

Observed result:

```text
mneme: http://127.0.0.1:8000/mcp (HTTP) - Pending approval
```

Detailed check:

```bash
claude mcp get mneme
```

Observed result:

```text
Scope: Project config (shared via .mcp.json)
Status: Pending approval (run `claude` to approve)
Type: http
URL: http://127.0.0.1:8000/mcp
```

This means the MCP config path and format are correct. The remaining MCP step is to run `claude` from the project directory and approve the project-scoped server.

## Current Machine Status

The local runtime prerequisites are now installed:

```text
Homebrew: installed
PostgreSQL: postgresql@17 installed and running
pgvector: installed, extension enabled in mneme database
uv: installed at /Users/mac/.local/bin/uv
Python: uv-managed CPython 3.14.6
```

The service starts successfully when launched with network permissions, and `/health` returns:

```json
{"status":"ok","service":"mneme"}
```

Remaining local setup gap:

```text
DEEPSEEK_API_KEY: still placeholder
EMBED_API_KEY: still placeholder
```

Real `remember` / `recall` / Sleep LLM calls require filling those keys.

## Fixed During This Pass

1. Added project MCP config:

```text
.mcp.json
```

2. Updated MCP docs from draft to verified Claude Code project config format:

```text
docs/mcp-config-example.json
docs/QUICKSTART.md
```

3. Fixed embedding key naming mismatch:

```text
OPENAI_API_KEY -> EMBED_API_KEY
```

The code uses `EMBED_API_KEY`, `EMBED_BASE_URL`, and `EMBED_MODEL`, so the docs now match the implementation.

4. Updated setup script to create the runtime log directory:

```bash
mkdir -p logs
```

5. Replaced deprecated UTC timestamp calls:

```text
datetime.utcnow() -> datetime.now(timezone.utc)
```

Touched files:

```text
src/mneme/memory/store.py
src/mneme/sleep/agent.py
src/mneme/sleep/staging.py
src/mneme/sleep/tools.py
```

## Next Required Setup Steps

Run the existing setup script when dependencies need to be repaired:

```bash
cd /Users/mac/dream
bash scripts/setup.sh
```

After setup, edit `.env`:

```bash
$EDITOR .env
```

Minimum required values:

```env
DEEPSEEK_API_KEY=...
EMBED_API_KEY=...
DATABASE_URL=postgresql+asyncpg://mac@localhost:5432/mneme
```

Then start the service:

```bash
/Users/mac/.local/bin/uv run python -m mneme
```

Verify health:

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok","service":"mneme"}
```

## Claude Code Approval

After the service is running:

```bash
cd /Users/mac/dream
claude
```

Approve the project-scoped `.mcp.json` server when prompted.

Then verify inside Claude Code:

```text
/mcp
```

Expected server:

```text
mneme
```

Expected tools:

```text
mcp__mneme__remember
mcp__mneme__recall
mcp__mneme__list_memory
mcp__mneme__forget
```

## Remaining Code Risks To Validate After Environment Install

Validation already run:

```bash
/Users/mac/.local/bin/uv run pytest
# 2 passed, 9 skipped

/Users/mac/.local/bin/uv run python -c "from mneme.awake.agent import get_awake_agent; get_awake_agent(); print('awake ok')"
# awake ok

/Users/mac/.local/bin/uv run python -c "from mneme.sleep.agent import get_sleep_graph; get_sleep_graph(); print('sleep graph ok')"
# sleep graph ok
```

Useful checks after changing dependencies:

```bash
uv run python -c "from langgraph.prebuilt import create_react_agent; import inspect; print(inspect.signature(create_react_agent))"
uv run python -c "from mneme.awake.agent import get_awake_agent; get_awake_agent(); print('awake ok')"
uv run python -c "from mneme.sleep.agent import get_sleep_graph; get_sleep_graph(); print('sleep graph ok')"
uv run pytest
```

Then run DB-backed checks after PostgreSQL and pgvector are ready:

```bash
uv run pytest --run-integration
```

The known higher-risk areas are still the ones listed in `docs/CODE_REVIEW.md`:

- LangGraph `create_react_agent` signature
- LangGraph `StateGraph` API
- FastMCP constructor / Starlette mount behavior
- pgvector cosine-distance query syntax
- raw SQL vector binding in sleep consolidation
