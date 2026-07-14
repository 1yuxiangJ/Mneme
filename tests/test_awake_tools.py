from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from typing import Any

import pytest

from mneme.awake import tools


class _SessionContext(AbstractAsyncContextManager[object]):
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


def _sessionmaker() -> Any:
    return lambda: _SessionContext()


@pytest.mark.asyncio
async def test_duplicate_search_does_not_increment_usage(monkeypatch):
    async def fake_search(_session: object, _query: str, limit: int):
        assert limit == 5
        return [SimpleNamespace(
            id=7,
            content="Existing fact.",
            tags=["test"],
            confidence=3,
            stability="long_term",
            salience=3,
            distance=0.01,
        )]

    async def fail_mark_used(_session: object, _ids: list[int]) -> None:
        raise AssertionError("Remember duplicate search must not count as Recall usage")

    monkeypatch.setattr(tools, "session_factory", _sessionmaker)
    monkeypatch.setattr(tools, "semantic_search_archival", fake_search)
    monkeypatch.setattr(tools, "mark_archival_used", fail_mark_used)

    result = await tools.find_archival_duplicates.ainvoke({"query": "Existing fact."})

    assert result["results"][0]["id"] == 7


@pytest.mark.asyncio
async def test_recall_search_increments_usage(monkeypatch):
    marked: list[int] = []

    async def fake_search(_session: object, _query: str, limit: int):
        return [SimpleNamespace(
            id=8,
            content="Relevant fact.",
            tags=["test"],
            confidence=3,
            stability="long_term",
            salience=2,
            distance=0.05,
        )]

    async def mark_used(_session: object, ids: list[int]) -> None:
        marked.extend(ids)

    monkeypatch.setattr(tools, "session_factory", _sessionmaker)
    monkeypatch.setattr(tools, "semantic_search_archival", fake_search)
    monkeypatch.setattr(tools, "mark_archival_used", mark_used)

    await tools.search_archival.ainvoke({"query": "Relevant fact.", "limit": 3})

    assert marked == [8]
