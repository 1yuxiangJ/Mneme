# Day 06 E2E Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the first real end-to-end Mneme loop: verify all MCP tools, add a manual Sleep trigger, expose enough inspection output to debug without DataGrip, document the flow, then commit and push.

**Architecture:** Keep the app service unchanged. Add a small testable Sleep CLI wrapper under `src/mneme/sleep/cli.py`, a thin executable script under `scripts/`, and focused tests that mock the expensive LLM-backed Sleep cycle. Use real smoke commands only during final verification.

**Tech Stack:** Python 3.11+, uv, FastAPI/FastMCP, LangGraph, SQLAlchemy async, PostgreSQL/pgvector, pytest, ruff.

---

### Task 1: Add Testable Manual Sleep Entrypoint

**Files:**
- Create: `src/mneme/sleep/cli.py`
- Create: `scripts/run_sleep_once.py`
- Create: `tests/test_sleep_cli.py`

- [ ] **Step 1: Write the failing CLI unit test**

Create `tests/test_sleep_cli.py` with tests that monkeypatch `run_sleep_cycle()` and verify JSON output plus exit codes:

```python
from __future__ import annotations

import json

import pytest

from mneme.sleep import cli


@pytest.mark.asyncio
async def test_run_once_prints_json_and_returns_zero(monkeypatch, capsys):
    async def fake_cycle():
        return {
            "status": "ok",
            "plan": ["reflect"],
            "reflection_preview": "user prefers concrete answers",
        }

    monkeypatch.setattr(cli, "run_sleep_cycle", fake_cycle)

    exit_code = await cli.run_once()

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["plan"] == ["reflect"]


@pytest.mark.asyncio
async def test_run_once_returns_one_on_error_status(monkeypatch, capsys):
    async def fake_cycle():
        return {"status": "error", "error": "boom"}

    monkeypatch.setattr(cli, "run_sleep_cycle", fake_cycle)

    exit_code = await cli.run_once()

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "boom"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
/Users/mac/.local/bin/uv run pytest tests/test_sleep_cli.py -q
```

Expected: FAIL because `mneme.sleep.cli` does not exist.

- [ ] **Step 3: Implement `src/mneme/sleep/cli.py`**

```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from mneme.sleep.agent import run_sleep_cycle


async def run_once() -> int:
    result: dict[str, Any] = await run_sleep_cycle()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result.get("status") == "error" else 0


def main() -> int:
    return asyncio.run(run_once())
```

- [ ] **Step 4: Implement `scripts/run_sleep_once.py`**

```python
#!/usr/bin/env python
from __future__ import annotations

import sys

from mneme.sleep.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the focused test**

Run:

```bash
/Users/mac/.local/bin/uv run pytest tests/test_sleep_cli.py -q
```

Expected: PASS.

### Task 2: Add Memory Inspection Helper

**Files:**
- Create: `src/mneme/memory/inspect.py`
- Create: `scripts/inspect_memory.py`
- Create: `tests/test_memory_inspect.py`

- [ ] **Step 1: Write a focused formatting test**

Create `tests/test_memory_inspect.py` with a pure formatter test:

```python
from __future__ import annotations

from mneme.memory.inspect import format_snapshot


def test_format_snapshot_includes_core_archival_and_ops():
    rendered = format_snapshot({
        "core_blocks": [{"label": "preferences", "value": "direct answers", "version": 2}],
        "archival_facts": [{"id": 3, "content": "likes concrete Chinese explanations", "tags": ["preference"]}],
        "recent_ops": [{"op_type": "remember", "actor": "awake_agent", "target_id": "3"}],
    })

    assert "core_blocks" in rendered
    assert "preferences" in rendered
    assert "archival_facts" in rendered
    assert "likes concrete" in rendered
    assert "recent_ops" in rendered
    assert "remember" in rendered
```

- [ ] **Step 2: Implement snapshot collection and formatting**

`src/mneme/memory/inspect.py` should expose:

```python
async def collect_snapshot(limit: int = 10) -> dict[str, Any]: ...
def format_snapshot(snapshot: dict[str, Any]) -> str: ...
async def run(limit: int = 10) -> int: ...
def main() -> int: ...
```

Use SQLAlchemy async session, read core blocks, non-deleted archival facts ordered by id desc, and recent ops ordered by ts desc.

- [ ] **Step 3: Add `scripts/inspect_memory.py`**

The script should call `mneme.memory.inspect.main()` and print a JSON snapshot.

- [ ] **Step 4: Run the focused test**

Run:

```bash
/Users/mac/.local/bin/uv run pytest tests/test_memory_inspect.py -q
```

Expected: PASS.

### Task 3: Real Local Smoke

**Files:**
- Modify: `docs/construction-log/2026-07-02-day-06-e2e-hardening.md`

- [ ] **Step 1: Verify service health**

Run:

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected JSON includes `"status":"ok"`.

- [ ] **Step 2: Verify Claude Code MCP connection**

Run:

```bash
scripts/claude-mneme.sh mcp list
```

Expected output includes `mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected`.

- [ ] **Step 3: Verify real MCP `forget`**

Use Claude Code with allowed `mcp__mneme__forget` to soft-delete a known smoke-test fact, then verify with recall or DB inspection that it is not returned as active archival memory.

- [ ] **Step 4: Trigger real Sleep once**

Run:

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
```

Expected: JSON with `"status": "ok"` or `"status": "aborted"` but not `"status": "error"`.

- [ ] **Step 5: Inspect memory state**

Run:

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py
```

Expected: output includes `core_blocks`, `archival_facts`, and `recent_ops`.

### Task 4: Docs, Quality Gate, Commit, Push

**Files:**
- Modify: `README.md`
- Modify: `docs/QUICKSTART.md`
- Create: `docs/construction-log/2026-07-02-day-06-e2e-hardening.md`

- [ ] **Step 1: Document the new scripts**

Add commands for:

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py
```

- [ ] **Step 2: Run quality checks**

Run:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run pytest --run-integration
```

Expected: both pass. If `mypy` still fails, record it as existing typed debt unless this task explicitly fixes it.

- [ ] **Step 3: Commit**

Run:

```bash
git add README.md docs src scripts tests
git commit -m "feat: harden mneme e2e demo flow"
```

- [ ] **Step 4: Push**

Run:

```bash
git push
```

Expected: push succeeds to `origin/main`.

---

## Self-Review

- Spec coverage: covers manual Sleep entrypoint, real MCP forget verification, inspectability, docs, local quality checks, commit, push.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: functions are named consistently as `run_once`, `main`, `collect_snapshot`, and `format_snapshot`.
