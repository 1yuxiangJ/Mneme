"""Tests for sleep.staging snapshot + atomic swap.

Requires PG + pgvector + mneme_test database. Run with:

    pytest --run-integration -m integration
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from mneme.sleep import tools as sleep_tools
from mneme.sleep.staging import atomic_swap, cleanup_staging, snapshot_to_staging
from mneme.sleep.tools import (
    find_consolidation_clusters,
    get_core_refresh_context,
    get_promote_candidates,
)

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


async def _insert_signal_archival(
    session,
    content: str,
    confidence: int,
    stability: str,
    salience: int,
    use_count: int,
) -> int:
    return int((await session.execute(text(
        """
        INSERT INTO archival_facts (
            content, tags, confidence, stability, salience, source, embedding,
            use_count
        )
        VALUES (
            :content, ARRAY['test'], :confidence, :stability, :salience, 'test',
            CAST(:embedding AS vector), :use_count
        )
        RETURNING id
        """
    ), {
        "content": content,
        "confidence": confidence,
        "stability": stability,
        "salience": salience,
        "use_count": use_count,
        "embedding": _vector_literal(),
    })).scalar_one())


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
async def test_promote_candidates_require_long_term_salient_explicit_memory(
    integration_session,
):
    """Promotion candidates must be explicit, durable, highly salient, and frequently used."""
    stable_id = await _insert_signal_archival(
        integration_session,
        "User prefers direct engineering explanations.",
        confidence=3,
        stability="long_term",
        salience=3,
        use_count=6,
    )
    await _insert_signal_archival(
        integration_session,
        "User likes a specific restaurant's fries.",
        confidence=3,
        stability="long_term",
        salience=2,
        use_count=12,
    )
    await _insert_signal_archival(
        integration_session,
        "User currently mainly plays CS2.",
        confidence=3,
        stability="stage",
        salience=2,
        use_count=9,
    )
    await _insert_signal_archival(
        integration_session,
        "User's local Mneme path is /Users/mac/dream.",
        confidence=3,
        stability="long_term",
        salience=1,
        use_count=9,
    )
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    candidates = await get_promote_candidates(integration_session)

    assert [item["id"] for item in candidates] == [stable_id]
    assert candidates[0]["stability"] == "long_term"
    assert candidates[0]["salience"] == 3


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
async def test_atomic_swap_merges_existing_archival_fields_by_owner(
    integration_session,
):
    """Sleep semantic edits and Awake usage/deletion updates must both survive."""
    recalled_id = await _insert_signal_archival(
        integration_session,
        "Original wording.",
        confidence=3,
        stability="long_term",
        salience=3,
        use_count=5,
    )
    forgotten_id = await _insert_signal_archival(
        integration_session,
        "Awake will forget this during Sleep.",
        confidence=3,
        stability="long_term",
        salience=2,
        use_count=1,
    )
    await integration_session.commit()

    snapshot_ts = await snapshot_to_staging(integration_session)

    # Sleep owns semantic consolidation and demotion in staging.
    await integration_session.execute(text(
        """
        UPDATE archival_facts_staging
        SET content = 'Sleep consolidated wording.', is_deleted = TRUE
        WHERE id = :id
        """
    ), {"id": recalled_id})

    # Awake owns live usage signals and can forget an existing main-table fact.
    await integration_session.execute(text(
        """
        UPDATE archival_facts
        SET use_count = use_count + 1,
            last_used_at = TIMESTAMPTZ '2026-07-11 12:00:00+08'
        WHERE id = :id
        """
    ), {"id": recalled_id})
    await integration_session.execute(text(
        "UPDATE archival_facts SET is_deleted = TRUE WHERE id = :id"
    ), {"id": forgotten_id})
    await integration_session.commit()

    await atomic_swap(integration_session, snapshot_ts)

    recalled = (await integration_session.execute(text(
        """
        SELECT content, use_count, last_used_at, is_deleted
        FROM archival_facts WHERE id = :id
        """
    ), {"id": recalled_id})).one()
    forgotten = (await integration_session.execute(text(
        "SELECT is_deleted FROM archival_facts WHERE id = :id"
    ), {"id": forgotten_id})).scalar_one()

    assert recalled.content == "Sleep consolidated wording."
    assert recalled.use_count == 6
    assert recalled.last_used_at is not None
    assert recalled.is_deleted is True
    assert forgotten is True


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
async def test_core_refresh_logs_are_pending_until_swap_commits(integration_session):
    """Core refresh should rewrite staging core and log only after swap succeeds."""
    from mneme.sleep.tools import apply_core_refreshes

    snapshot_ts = await snapshot_to_staging(integration_session)

    pending_ops = await apply_core_refreshes(integration_session, [{
        "block": "preferences",
        "decision": "REFRESH",
        "new_block_value": "User prefers direct, concrete engineering explanations.",
        "reason": "remove stale and over-specific core details",
    }])
    pending_ops.append(sleep_tools.draft_core_refresh_checkpoint(
        {
            "evidence_mode": "all_active",
            "active_archival_count": 0,
            "supporting_archival": [],
            "ops_since_last_refresh": [],
        },
        [{"decision": "REFRESH", "block": "preferences"}],
    ))

    staged_value = (await integration_session.execute(text(
        "SELECT value FROM core_blocks_staging WHERE label = 'preferences'"
    ))).scalar_one()
    before_swap = (await integration_session.execute(text(
        "SELECT count(*) FROM memory_ops_log"
    ))).scalar_one()

    await atomic_swap(integration_session, snapshot_ts, pending_ops=pending_ops)

    op_targets = (await integration_session.execute(text(
        "SELECT target_id FROM memory_ops_log "
        "WHERE op_type = 'sleep_core_refresh' ORDER BY id"
    ))).scalars().all()

    assert staged_value == "User prefers direct, concrete engineering explanations."
    assert before_swap == 0
    assert op_targets == ["preferences", "__checkpoint__"]


@pytest.mark.asyncio
async def test_core_refresh_context_loads_all_facts_and_only_ops_after_checkpoint(
    integration_session,
):
    fact_ids = [
        await _insert_archival(integration_session, f"Active fact {index}.", axis=index)
        for index in range(3)
    ]
    await integration_session.execute(text(
        "UPDATE core_blocks SET value = 'User profile exists.' WHERE label = 'background'"
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES (
            'sleep_core_refresh', 'sleep_agent', 'core', '__checkpoint__',
            'previous refresh check'
        )
        """
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES ('remember', 'awake_agent', 'archival', :target_id, 'new fact')
        """
    ), {"target_id": str(fact_ids[-1])})
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    context = await get_core_refresh_context(
        integration_session,
        all_facts_threshold=200,
    )

    assert context["refresh_required"] is True
    assert context["evidence_mode"] == "all_active"
    assert {fact["id"] for fact in context["supporting_archival"]} == set(fact_ids)
    assert [op["op_type"] for op in context["ops_since_last_refresh"]] == [
        "remember"
    ]


@pytest.mark.asyncio
async def test_core_refresh_context_uses_adaptive_per_core_evidence(
    integration_session,
    monkeypatch,
):
    semantic_id = await _insert_archival(
        integration_session,
        "Semantic match for the background block.",
        axis=0,
    )
    high_signal_id = await _insert_archival(
        integration_session,
        "Global high-signal preference.",
        axis=1,
    )
    changed_id = await _insert_archival(
        integration_session,
        "Recently changed stage-specific fact.",
        axis=2,
    )
    await integration_session.execute(text(
        """
        UPDATE archival_facts SET confidence = 2, salience = 2
        WHERE id = :id
        """
    ), {"id": semantic_id})
    await integration_session.execute(text(
        """
        UPDATE archival_facts
        SET confidence = 3, stability = 'long_term', salience = 3, use_count = 10
        WHERE id = :id
        """
    ), {"id": high_signal_id})
    await integration_session.execute(text(
        """
        UPDATE archival_facts SET confidence = 2, stability = 'stage', salience = 2
        WHERE id = :id
        """
    ), {"id": changed_id})
    await integration_session.execute(text(
        "UPDATE core_blocks SET value = 'Backend developer profile.' WHERE label = 'background'"
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES (
            'sleep_core_refresh', 'sleep_agent', 'core', '__checkpoint__',
            'previous refresh check'
        )
        """
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES ('remember', 'awake_agent', 'archival', :target_id, 'new fact')
        """
    ), {"target_id": str(changed_id)})
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    async def fake_embed_text(_text: str) -> list[float]:
        vector = [0.0] * 1024
        vector[0] = 1.0
        return vector

    monkeypatch.setattr(sleep_tools, "embed_text", fake_embed_text)

    context = await get_core_refresh_context(
        integration_session,
        all_facts_threshold=2,
        per_block_limit=1,
        high_signal_limit=1,
    )

    facts = {fact["id"]: fact for fact in context["supporting_archival"]}
    assert context["evidence_mode"] == "adaptive"
    assert set(facts) == {semantic_id, high_signal_id, changed_id}
    assert "semantic:background" in facts[semantic_id]["evidence_reasons"]
    assert "global_high_signal" in facts[high_signal_id]["evidence_reasons"]
    assert "changed_since_refresh" in facts[changed_id]["evidence_reasons"]


@pytest.mark.asyncio
async def test_core_refresh_context_skips_when_checkpoint_has_no_new_changes(
    integration_session,
):
    await _insert_archival(integration_session, "Existing fact.")
    await integration_session.execute(text(
        "UPDATE core_blocks SET value = 'Existing core.' WHERE label = 'background'"
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES (
            'sleep_core_refresh', 'sleep_agent', 'core', '__checkpoint__',
            'latest refresh check'
        )
        """
    ))
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    context = await get_core_refresh_context(integration_session)

    assert context["refresh_required"] is False
    assert context["skip_reason"] == "no_relevant_changes_since_checkpoint"
    assert context["supporting_archival"] == []


@pytest.mark.asyncio
async def test_core_refresh_context_reads_awake_fact_inserted_after_snapshot(
    integration_session,
):
    await integration_session.execute(text(
        "UPDATE core_blocks SET value = 'Existing core.' WHERE label = 'background'"
    ))
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES (
            'sleep_core_refresh', 'sleep_agent', 'core', '__checkpoint__',
            'previous refresh check'
        )
        """
    ))
    await integration_session.commit()
    await snapshot_to_staging(integration_session)

    inserted_id = await _insert_archival(
        integration_session,
        "Awake inserted this after the Sleep snapshot.",
    )
    await integration_session.execute(text(
        """
        INSERT INTO memory_ops_log (
            op_type, actor, target_kind, target_id, reason
        ) VALUES ('remember', 'awake_agent', 'archival', :target_id, 'new fact')
        """
    ), {"target_id": str(inserted_id)})
    await integration_session.commit()

    context = await get_core_refresh_context(integration_session)

    facts = {fact["id"]: fact for fact in context["supporting_archival"]}
    assert context["refresh_required"] is True
    assert inserted_id in facts
    assert "changed_since_refresh" in facts[inserted_id]["evidence_reasons"]


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
