from __future__ import annotations

import json
from types import SimpleNamespace

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
    assert "/api/console/bulk-remember/run" in response.text


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


def test_console_bulk_remember_api_enqueues_seed_jobs(monkeypatch, tmp_path):
    from mneme import console

    monkeypatch.setattr(settings, "memory_write_worker_enabled", False)
    seed_file = tmp_path / "seed.jsonl"
    seed_file.write_text(
        "\n".join([
            json.dumps({
                "content": "用户偏好直接、具体的中文解释。",
                "tags": ["seed_demo", "communication"],
                "confidence": 3,
                "stability": "long_term",
                "salience": 3,
            }, ensure_ascii=False),
            json.dumps({
                "content": "用户在学习系统设计时喜欢先看整体链路。",
                "tags": ["seed_demo", "study"],
                "confidence": 2,
                "stability": "stage",
                "salience": 2,
            }, ensure_ascii=False),
        ]),
        encoding="utf-8",
    )
    calls: list[tuple[str, str, dict[str, object]]] = []

    async def fake_enqueue_awake_write(
        operation: str,
        command: str,
        payload: dict[str, object],
    ) -> SimpleNamespace:
        calls.append((operation, command, payload))
        return SimpleNamespace(id=len(calls), status="pending")

    monkeypatch.setattr(console, "BULK_MEMORY_SEED_PATH", seed_file)
    monkeypatch.setattr(console, "enqueue_awake_write", fake_enqueue_awake_write)

    client = TestClient(app)
    response = client.post("/api/console/bulk-remember/run")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dataset_count"] == 2
    assert body["accepted_count"] == 2
    assert [call[0] for call in calls] == ["remember", "remember"]
    assert "First check for near-duplicates" in calls[0][1]
    assert calls[0][2]["content"] == "用户偏好直接、具体的中文解释。"


def test_bulk_memory_seed_dataset_contains_100_valid_items():
    from mneme import console

    items = console.load_bulk_memory_seed()

    assert len(items) == 100
    assert len({item["content"] for item in items}) == 100
    assert all("seed_demo" in item["tags"] for item in items)
    assert all(item["confidence"] in {1, 2, 3} for item in items)
    assert all(item["stability"] in {"temporary", "stage", "long_term"} for item in items)
    assert all(item["salience"] in {1, 2, 3} for item in items)
