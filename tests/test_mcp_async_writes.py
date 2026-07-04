from __future__ import annotations

import asyncio

import pytest

from mneme import mcp_server


@pytest.mark.asyncio
async def test_remember_returns_accepted_without_awaiting_awake(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_awake(command: str) -> dict[str, str]:
        started.set()
        await release.wait()
        return {"status": "ok"}

    monkeypatch.setattr(mcp_server, "_run_awake", slow_awake)

    result = await mcp_server.remember("User prefers direct answers.", ["preference"], 3)

    assert result["status"] == "accepted"
    assert result["mode"] == "async"
    assert result["operation"] == "remember"
    assert started.is_set() is False

    await asyncio.wait_for(started.wait(), timeout=1)
    release.set()


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
