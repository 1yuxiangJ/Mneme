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
