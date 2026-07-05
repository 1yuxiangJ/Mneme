from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mneme import mcp_server
from mneme.memory.store import CoreBlockSnapshot, MemoryOverview


@pytest.mark.asyncio
async def test_remember_enqueues_durable_job_without_awaiting_awake(monkeypatch):
    captured: dict[str, object] = {}

    async def fail_awake(command: str) -> dict[str, str]:
        raise AssertionError(f"remember should not call Awake directly: {command}")

    async def enqueue_awake_write(operation, command, payload):
        captured["operation"] = operation
        captured["command"] = command
        captured["payload"] = payload
        return SimpleNamespace(id=42, status="pending", dedupe_key="abc123")

    monkeypatch.setattr(mcp_server, "_run_awake", fail_awake)
    monkeypatch.setattr(mcp_server, "enqueue_awake_write", enqueue_awake_write)

    result = await mcp_server.remember("User prefers direct answers.", ["preference"], 3)

    assert result["status"] == "accepted"
    assert result["mode"] == "durable_async"
    assert result["operation"] == "remember"
    assert result["job_id"] == 42
    assert captured["operation"] == "remember"
    assert "User prefers direct answers." in str(captured["command"])


@pytest.mark.asyncio
async def test_remember_command_includes_memory_signals(monkeypatch):
    captured_command = ""

    async def enqueue_awake_write(operation, command, payload):
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(id=43, status="pending", dedupe_key="def456")

    monkeypatch.setattr(mcp_server, "enqueue_awake_write", enqueue_awake_write)

    result = await mcp_server.remember(
        "User currently mainly plays CS2.",
        ["hobby", "gaming"],
        confidence=3,
        stability="stage",
        salience=2,
    )

    assert result["status"] == "accepted"
    assert "confidence: 3" in captured_command
    assert "stability: stage" in captured_command
    assert "salience: 2" in captured_command


@pytest.mark.asyncio
async def test_forget_enqueues_durable_job(monkeypatch):
    captured: dict[str, object] = {}

    async def enqueue_awake_write(operation, command, payload):
        captured["operation"] = operation
        captured["command"] = command
        captured["payload"] = payload
        return SimpleNamespace(id=44, status="pending", dedupe_key="ghi789")

    monkeypatch.setattr(mcp_server, "enqueue_awake_write", enqueue_awake_write)

    result = await mcp_server.forget(7, "outdated")

    assert result["status"] == "accepted"
    assert result["mode"] == "durable_async"
    assert result["operation"] == "forget"
    assert result["job_id"] == 44
    assert captured["operation"] == "forget"
    assert captured["payload"] == {"fact_id": 7, "reason": "outdated"}


@pytest.mark.asyncio
async def test_recall_still_awaits_awake(monkeypatch):
    awaited = False

    async def awake(command: str) -> dict[str, str]:
        nonlocal awaited
        awaited = True
        return {"status": "ok", "final_message": command}

    monkeypatch.setattr(mcp_server, "_run_awake", awake)

    result = await mcp_server.recall("style", 3)

    assert awaited is True
    assert result["status"] == "ok"
    assert "recall" in result["final_message"]


@pytest.mark.asyncio
async def test_list_memory_reads_database_without_awake(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSessionMaker:
        def __call__(self):
            return FakeSession()

    async def fail_awake(command: str) -> dict[str, str]:
        raise AssertionError(f"list_memory should not call Awake: {command}")

    async def fake_overview(session):
        return MemoryOverview(
            core_blocks=[
                CoreBlockSnapshot(
                    label="background",
                    value="Java backend developer.",
                    char_limit=2000,
                    version=2,
                    updated_at=datetime(2026, 7, 5, tzinfo=UTC),
                )
            ],
            archival_count=1,
        )

    async def fake_archival_facts(session, limit: int):
        return [
            SimpleNamespace(
                id=7,
                content="User prefers direct Chinese explanations.",
                tags=["communication", "preference"],
                confidence=3,
                stability="long_term",
                salience=3,
                source="test",
                created_at=datetime(2026, 7, 5, tzinfo=UTC),
                last_used_at=None,
                use_count=0,
            )
        ]

    monkeypatch.setattr(mcp_server, "_run_awake", fail_awake)
    monkeypatch.setattr(mcp_server, "get_sessionmaker", lambda: FakeSessionMaker(), raising=False)
    monkeypatch.setattr(mcp_server, "get_memory_overview", fake_overview, raising=False)
    monkeypatch.setattr(mcp_server, "list_archival_facts", fake_archival_facts, raising=False)

    result = await mcp_server.list_memory()

    assert result["status"] == "ok"
    assert result["mode"] == "direct_db"
    assert result["archival_total"] == 1
    assert result["core_blocks"][0]["label"] == "background"
    assert result["core_blocks"][0]["value"] == "Java backend developer."
    assert result["archival_facts"][0]["id"] == 7
    assert result["archival_facts"][0]["stability"] == "long_term"
    assert result["archival_facts"][0]["salience"] == 3
