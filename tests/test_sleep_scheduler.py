"""Pure-unit tests for Sleep scheduler cost controls."""
from __future__ import annotations

import importlib


def test_sleep_scheduler_is_disabled_by_default(monkeypatch):
    """Starting the service should not auto-schedule paid Sleep cycles by default."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("EMBED_API_KEY", "test-embed-key")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test@localhost:5432/mneme"
    )

    import mneme.config
    import mneme.sleep.scheduler

    importlib.reload(mneme.config)
    scheduler = importlib.reload(mneme.sleep.scheduler)

    assert scheduler.start_sleep_scheduler() is None
