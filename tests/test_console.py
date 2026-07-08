from __future__ import annotations

from starlette.testclient import TestClient

from mneme.config import settings
from mneme.main import app


def test_console_page_is_served(monkeypatch):
    monkeypatch.setattr(settings, "memory_write_worker_enabled", False)

    client = TestClient(app)
    response = client.get("/console")

    assert response.status_code == 200
    assert "Mneme Console" in response.text
    assert "/api/console/snapshot" in response.text


def test_console_snapshot_api_returns_dashboard_payload(monkeypatch):
    from mneme import console

    monkeypatch.setattr(settings, "memory_write_worker_enabled", False)

    async def fake_snapshot() -> dict[str, object]:
        return {
            "status": "ok",
            "memory": {"counts": {"active_archival_facts": 2}},
            "jobs": {"jobs": [{"id": 1, "status": "succeeded"}]},
        }

    monkeypatch.setattr(console, "collect_console_snapshot", fake_snapshot)

    client = TestClient(app)
    response = client.get("/api/console/snapshot")

    assert response.status_code == 200
    assert response.json()["memory"]["counts"]["active_archival_facts"] == 2
    assert response.json()["jobs"]["jobs"][0]["status"] == "succeeded"


def test_console_sleep_run_api_returns_cycle_summary(monkeypatch):
    from mneme import console

    monkeypatch.setattr(settings, "memory_write_worker_enabled", False)

    async def fake_run_sleep_cycle() -> dict[str, object]:
        return {
            "status": "ok",
            "plan": ["promote", "reflect"],
            "promote_count": 1,
        }

    monkeypatch.setattr(console, "run_sleep_cycle", fake_run_sleep_cycle)

    client = TestClient(app)
    response = client.post("/api/console/sleep/run")

    assert response.status_code == 200
    assert response.json()["summary"]["plan"] == ["promote", "reflect"]
    assert response.json()["summary"]["promote_count"] == 1
