"""Pure-unit tests for LLM client construction."""
from __future__ import annotations

import importlib


def test_dashscope_embedder_keeps_raw_string_input(monkeypatch):
    """DashScope compatible embeddings require raw string input, not token arrays."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("EMBED_API_KEY", "test-embed-key")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test@localhost:5432/mneme"
    )

    import mneme.config
    import mneme.llm.client

    importlib.reload(mneme.config)
    importlib.reload(mneme.llm.client)

    embedder = mneme.llm.client.get_embedder()

    assert embedder.check_embedding_ctx_length is False
