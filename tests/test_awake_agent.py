from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mneme.awake import agent as awake_agent


class CapturingAgent:
    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None

    async def ainvoke(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.config = config
        return {"messages": [type("Msg", (), {"content": "ok"})()]}


@pytest.mark.asyncio
async def test_run_awake_passes_recursion_limit(monkeypatch):
    fake = CapturingAgent()
    monkeypatch.setattr(awake_agent, "get_awake_agent", lambda: fake)
    monkeypatch.setattr(awake_agent.settings, "awake_react_recursion_limit", 8)
    monkeypatch.setattr(awake_agent.settings, "awake_overall_timeout_seconds", 45.0)

    result = await awake_agent.run_awake("list memory")

    assert result["final_message"] == "ok"
    assert fake.config == {"recursion_limit": 8}


@pytest.mark.asyncio
async def test_run_awake_returns_timeout_status(monkeypatch):
    class SlowAgent:
        async def ainvoke(
            self,
            payload: dict[str, Any],
            config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            await asyncio.sleep(1)
            return {"messages": []}

    monkeypatch.setattr(awake_agent, "get_awake_agent", lambda: SlowAgent())
    monkeypatch.setattr(awake_agent.settings, "awake_react_recursion_limit", 8)
    monkeypatch.setattr(awake_agent.settings, "awake_overall_timeout_seconds", 0.01)

    result = await awake_agent.run_awake("remember something")

    assert result["status"] == "timeout"
    assert "timed out" in result["final_message"]
