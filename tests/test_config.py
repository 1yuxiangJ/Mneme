"""Pure-unit tests for mneme.config (no DB / no LLM)."""
from __future__ import annotations

import importlib


def test_settings_reads_env_vars(monkeypatch):
    """Settings should pick up required env vars via pydantic-settings."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("EMBED_API_KEY", "test-embed-key")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test@localhost:5432/mneme"
    )

    import mneme.config
    importlib.reload(mneme.config)

    assert mneme.config.settings.deepseek_api_key == "test-deepseek-key"
    assert mneme.config.settings.embed_api_key == "test-embed-key"
    assert "asyncpg" in mneme.config.settings.database_url


def test_sleep_defaults(monkeypatch):
    """Sleep agent defaults match PLAN.md §8.1."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("EMBED_API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")

    import mneme.config
    importlib.reload(mneme.config)

    assert mneme.config.settings.sleep_idle_threshold_seconds == 1800
    assert mneme.config.settings.sleep_daily_cron_hour == 3
    assert mneme.config.settings.sleep_max_wall_time_seconds == 300
    assert mneme.config.settings.sleep_min_archival_count == 10
    assert mneme.config.settings.sleep_scheduler_enabled is False
    assert mneme.config.settings.core_refresh_all_facts_threshold == 200
    assert mneme.config.settings.core_refresh_per_block_limit == 8
    assert mneme.config.settings.core_refresh_high_signal_limit == 10
