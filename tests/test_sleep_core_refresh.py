from __future__ import annotations

import time
from typing import Any

import pytest

from mneme.sleep import agent, tools


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


def _sessionmaker():
    return lambda: _SessionContext()


@pytest.mark.asyncio
async def test_plan_always_includes_core_refresh(monkeypatch):
    async def fake_summary(_session: object, _last_cycle: object):
        return tools.StateSummary([], 10, 0, 0, False)

    async def fake_llm(_prompt: str) -> dict[str, Any]:
        return {"phases": ["promote", "reflect"], "reason": "test"}

    monkeypatch.setattr(agent, "get_sessionmaker", _sessionmaker)
    monkeypatch.setattr(agent.tools, "summarize_state", fake_summary)
    monkeypatch.setattr(agent, "_llm_json", fake_llm)

    result = await agent.node_plan({"deadline_ts": time.monotonic() + 10})

    assert result["plan"] == ["promote", "core_refresh", "reflect"]


@pytest.mark.asyncio
async def test_plan_includes_demote_when_stale_candidates_exist(monkeypatch):
    async def fake_summary(_session: object, _last_cycle: object):
        return tools.StateSummary([], 10, 0, 1, False)

    async def fake_llm(_prompt: str) -> dict[str, Any]:
        return {"phases": ["promote", "reflect"], "reason": "omitted demote"}

    monkeypatch.setattr(agent, "get_sessionmaker", _sessionmaker)
    monkeypatch.setattr(agent.tools, "summarize_state", fake_summary)
    monkeypatch.setattr(agent, "_llm_json", fake_llm)

    result = await agent.node_plan({"deadline_ts": time.monotonic() + 10})

    assert result["plan"] == ["promote", "demote", "core_refresh", "reflect"]


@pytest.mark.asyncio
async def test_core_refresh_runs_even_when_plan_omits_it(monkeypatch):
    context = {
        "refresh_required": True,
        "skip_reason": None,
        "evidence_mode": "all_active",
        "checkpoint_op_id": None,
        "active_archival_count": 1,
        "core_blocks": [{"label": "background", "value": "Existing core."}],
        "supporting_archival": [{"id": 1, "content": "Evidence."}],
        "ops_since_last_refresh": [],
    }

    async def fake_context(_session: object, **_kwargs: object):
        return context

    async def fake_llm(_prompt: str) -> dict[str, Any]:
        return {"actions": [{"block": "background", "decision": "KEEP"}]}

    async def fake_apply(_session: object, _actions: list[dict[str, Any]]):
        return []

    monkeypatch.setattr(agent, "get_sessionmaker", _sessionmaker)
    monkeypatch.setattr(agent.tools, "get_core_refresh_context", fake_context)
    monkeypatch.setattr(agent, "_llm_json", fake_llm)
    monkeypatch.setattr(agent.tools, "apply_core_refreshes", fake_apply)

    result = await agent.node_core_refresh({
        "plan": ["reflect"],
        "deadline_ts": time.monotonic() + 10,
        "pending_ops": [],
    })

    assert result["core_refresh_checked"] is True
    assert result["core_refresh_actions"][0]["decision"] == "KEEP"
    assert result["pending_ops"][-1]["target_id"] == "__checkpoint__"


@pytest.mark.asyncio
async def test_core_refresh_skips_llm_when_no_relevant_changes(monkeypatch):
    async def fake_context(_session: object, **_kwargs: object):
        return {
            "refresh_required": False,
            "skip_reason": "no_relevant_changes_since_checkpoint",
            "evidence_mode": "none",
            "core_blocks": [{"label": "background", "value": "Existing core."}],
            "supporting_archival": [],
            "ops_since_last_refresh": [],
        }

    async def fail_llm(_prompt: str) -> dict[str, Any]:
        raise AssertionError("LLM should not run without relevant changes")

    monkeypatch.setattr(agent, "get_sessionmaker", _sessionmaker)
    monkeypatch.setattr(agent.tools, "get_core_refresh_context", fake_context)
    monkeypatch.setattr(agent, "_llm_json", fail_llm)

    result = await agent.node_core_refresh({
        "plan": ["core_refresh", "reflect"],
        "deadline_ts": time.monotonic() + 10,
    })

    assert result["core_refresh_checked"] is True
    assert result["core_refresh_skip_reason"] == "no_relevant_changes_since_checkpoint"
    assert result["core_refresh_actions"] == []
