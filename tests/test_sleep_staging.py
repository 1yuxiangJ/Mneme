"""Tests for sleep.staging snapshot + atomic swap.

Requires PG + pgvector + mneme_test database. Run with:

    pytest --run-integration -m integration
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from mneme.sleep.staging import atomic_swap, cleanup_staging, snapshot_to_staging
from mneme.sleep.tools import find_consolidation_clusters

pytestmark = pytest.mark.integration


def _vector_literal(axis: int = 0) -> str:
    vec = [0.0] * 1024
    vec[axis] = 1.0
    return "[" + ",".join(str(v) for v in vec) + "]"


async def _insert_archival(session, content: str, axis: int = 0) -> int:
    return int((await session.execute(text(
        """
        INSERT INTO archival_facts (content, tags, confidence, source, embedding)
        VALUES (:content, ARRAY['test'], 3, 'test', CAST(:embedding AS vector))
        RETURNING id
        """
    ), {"content": content, "embedding": _vector_literal(axis)})).scalar_one())


async def _count_table(session, table: str) -> int:
    return int((await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())


@pytest.mark.asyncio
async def test_snapshot_creates_staging_tables(integration_session):
    """After snapshot_to_staging, *_staging tables exist with same rows as main."""
    await _insert_archival(integration_session, "Fact copied into staging.")
    await integration_session.commit()

    await snapshot_to_staging(integration_session)

    core_staging_exists = (await integration_session.execute(
        text("SELECT to_regclass('public.core_blocks_staging')")
    )).scalar_one()
    archival_staging_exists = (await integration_session.execute(
        text("SELECT to_regclass('public.archival_facts_staging')")
    )).scalar_one()

    assert core_staging_exists == "core_blocks_staging"
    assert archival_staging_exists == "archival_facts_staging"
    assert await _count_table(integration_session, "core_blocks_staging") == 5
    assert await _count_table(integration_session, "archival_facts_staging") == 1


@pytest.mark.asyncio
async def test_find_consolidation_clusters_uses_pgvector_distance(integration_session):
    """Sleep consolidation can compare vector params inside raw SQL."""
    first_id = await _insert_archival(
        integration_session,
        "User prefers concise technical answers.",
        axis=0,
    )
    second_id = await _insert_archival(
        integration_session,
        "User likes direct engineering explanations.",
        axis=0,
    )
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    clusters = await find_consolidation_clusters(
        integration_session,
        distance_threshold=0.01,
    )

    assert len(clusters) == 1
    assert {item["id"] for item in clusters[0]} == {first_id, second_id}


@pytest.mark.asyncio
async def test_atomic_swap_replaces_main(integration_session):
    """After swap, queries against main return rows that were written to staging."""
    snapshot_ts = await snapshot_to_staging(integration_session)
    await integration_session.execute(text(
        """
        UPDATE core_blocks_staging
        SET value = 'Sleep rewrote this block.',
            version = version + 1,
            last_writer = 'sleep_agent'
        WHERE label = 'background'
        """
    ))
    await integration_session.commit()

    await atomic_swap(integration_session, snapshot_ts)

    value = (await integration_session.execute(text(
        "SELECT value FROM core_blocks WHERE label = 'background'"
    ))).scalar_one()

    assert value == "Sleep rewrote this block."
    assert await _count_table(integration_session, "core_blocks_staging") == 0


@pytest.mark.asyncio
async def test_atomic_swap_merges_new_archival_during_cycle(integration_session):
    """Archival rows inserted by Awake during the cycle (created_at > snapshot_ts)
    are merged into the new main after swap."""
    snapshot_ts = await snapshot_to_staging(integration_session)
    inserted_id = await _insert_archival(
        integration_session,
        "Awake inserted this while Sleep was working.",
    )
    await integration_session.commit()

    await atomic_swap(integration_session, snapshot_ts)

    content = (await integration_session.execute(text(
        "SELECT content FROM archival_facts WHERE id = :id"
    ), {"id": inserted_id})).scalar_one_or_none()

    assert content == "Awake inserted this while Sleep was working."


@pytest.mark.asyncio
async def test_sleep_logs_are_pending_until_swap_commits(integration_session):
    """Sleep phase logs should only enter memory_ops_log after swap succeeds."""
    from mneme.sleep.tools import apply_resolutions

    snapshot_ts = await snapshot_to_staging(integration_session)

    pending_ops = await apply_resolutions(integration_session, [{
        "fix_block": "preferences",
        "new_block_value": "User prefers direct, concrete engineering explanations.",
        "reason": "remove contradiction with habits block",
    }])

    before_swap = (await integration_session.execute(text(
        "SELECT count(*) FROM memory_ops_log"
    ))).scalar_one()

    await atomic_swap(integration_session, snapshot_ts, pending_ops=pending_ops)

    op_type = (await integration_session.execute(text(
        "SELECT op_type FROM memory_ops_log WHERE target_id = 'preferences'"
    ))).scalar_one()

    assert before_swap == 0
    assert op_type == "sleep_resolve"


@pytest.mark.asyncio
async def test_snapshot_repairs_missing_archival_id_sequence(integration_session):
    """Sleep should recover if a previous swap left archival id default missing."""
    await integration_session.execute(text(
        "ALTER TABLE archival_facts ALTER COLUMN id DROP DEFAULT"
    ))
    await integration_session.execute(text(
        "DROP SEQUENCE IF EXISTS archival_facts_id_seq CASCADE"
    ))
    await integration_session.execute(text(
        """
        INSERT INTO archival_facts (id, content, tags, confidence, source, embedding)
        VALUES (42, 'Existing fact with explicit id.', ARRAY['test'], 3, 'test',
                CAST(:embedding AS vector))
        """
    ), {"embedding": _vector_literal()})
    await integration_session.commit()

    snapshot_ts = await snapshot_to_staging(integration_session)
    await atomic_swap(integration_session, snapshot_ts)

    new_id = await _insert_archival(
        integration_session,
        "Insert after repaired swap should get generated id.",
    )

    assert new_id > 42


@pytest.mark.asyncio
async def test_cleanup_staging_drops_tables(integration_session):
    """After cleanup, *_staging tables no longer exist."""
    await snapshot_to_staging(integration_session)

    await cleanup_staging(integration_session)

    core_staging_exists = (await integration_session.execute(
        text("SELECT to_regclass('public.core_blocks_staging')")
    )).scalar_one()
    archival_staging_exists = (await integration_session.execute(
        text("SELECT to_regclass('public.archival_facts_staging')")
    )).scalar_one()

    assert core_staging_exists is None
    assert archival_staging_exists is None
