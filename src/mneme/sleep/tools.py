"""Sleep agent's data-access helpers (NOT LangGraph @tools — direct calls).

The Sleep agent's StateGraph nodes call these helpers directly rather than
going through LLM tool-calling, because the orchestration is already a graph.
Each phase node uses an LLM call (with prompts from sleep.prompts) to make
decisions, then applies the decisions via these helpers.

All writes here go to the *_staging tables (not main). Atomic swap into main
happens in sleep.staging.atomic_swap.

POLICY: actor='sleep_agent' for every write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.memory.store import Actor, MemoryOpDraft

SLEEP_ACTOR: Actor = "sleep_agent"


def _vector_literal(value: Any) -> str:
    """Return a pgvector-compatible '[...]' literal from DB-returned values."""
    if isinstance(value, str):
        return value
    return "[" + ",".join(str(v) for v in value) + "]"


# =====================================================================
# Read-side: load data from staging for LLM decision making
# =====================================================================


@dataclass
class StateSummary:
    core_blocks: list[dict[str, Any]]
    archival_count: int
    new_archival_since_last_cycle: int
    stale_archival_count: int
    has_high_freq_archival: bool


async def summarize_state(
    session: AsyncSession,
    last_cycle_ts: datetime | None,
    stale_threshold_days: int = 90,
) -> StateSummary:
    """Build a state summary for the PLAN phase."""
    # Core blocks (read from main — Sleep doesn't need staging for read).
    cores = (await session.execute(text(
        "SELECT label, value, version, char_limit FROM core_blocks ORDER BY label"
    ))).all()
    core_blocks = [
        {
            "label": r.label,
            "value": r.value,
            "version": r.version,
            "char_limit": r.char_limit,
        }
        for r in cores
    ]

    archival_count = int((await session.execute(text(
        "SELECT count(*) FROM archival_facts WHERE is_deleted = FALSE"
    ))).scalar_one())

    new_count = 0
    if last_cycle_ts is not None:
        new_count = int((await session.execute(text(
            "SELECT count(*) FROM archival_facts "
            "WHERE created_at > :ts AND is_deleted = FALSE"
        ), {"ts": last_cycle_ts})).scalar_one())

    stale_cutoff = datetime.now(UTC) - timedelta(days=stale_threshold_days)
    stale_count = int((await session.execute(text(
        "SELECT count(*) FROM archival_facts "
        "WHERE is_deleted = FALSE "
        "AND (confidence <= 1 OR stability = 'temporary' OR salience <= 1) "
        "AND (last_used_at IS NULL OR last_used_at < :cutoff)"
    ), {"cutoff": stale_cutoff})).scalar_one())

    high_freq = bool((await session.execute(text(
        "SELECT 1 FROM archival_facts "
        "WHERE is_deleted = FALSE "
        "AND use_count >= 5 "
        "AND confidence >= 3 "
        "AND stability = 'long_term' "
        "AND salience >= 3 "
        "LIMIT 1"
    ))).first())

    return StateSummary(
        core_blocks=core_blocks,
        archival_count=archival_count,
        new_archival_since_last_cycle=new_count,
        stale_archival_count=stale_count,
        has_high_freq_archival=high_freq,
    )


async def find_consolidation_clusters(
    session: AsyncSession,
    distance_threshold: float = 0.15,
    max_clusters: int = 10,
) -> list[list[dict[str, Any]]]:
    """Find clusters of near-duplicate archival in staging.

    Naive O(N^2) for MVP. For MVP archival sizes (<1000), this is fine.
    Day 05+: replace with HNSW + clustering algorithm.
    """
    rows = (await session.execute(text(
        "SELECT id, content, embedding, tags, confidence, stability, salience "
        "FROM archival_facts_staging "
        "WHERE is_deleted = FALSE AND embedding IS NOT NULL"
    ))).all()

    if len(rows) < 2:
        return []

    # Greedy clustering: each pair within threshold goes into a cluster.
    visited: set[int] = set()
    clusters: list[list[dict[str, Any]]] = []

    for row_i in rows:
        if row_i.id in visited:
            continue
        cluster = [_row_to_dict(row_i)]
        visited.add(row_i.id)

        # Compute distances to remaining unvisited rows.
        cands = (await session.execute(text(
            "SELECT id, content, tags, confidence, stability, salience, "
            "embedding <=> CAST(:emb AS vector) AS dist "
            "FROM archival_facts_staging "
            "WHERE is_deleted = FALSE AND id != :self_id "
            "AND id != ALL(:visited) "
            "ORDER BY dist ASC LIMIT 5"
        ), {
            "emb": _vector_literal(row_i.embedding),
            "self_id": row_i.id,
            "visited": list(visited),
        })).all()

        for c in cands:
            if c.dist < distance_threshold:
                cluster.append({
                    "id": c.id,
                    "content": c.content,
                    "tags": list(c.tags or []),
                    "confidence": c.confidence,
                    "stability": c.stability,
                    "salience": c.salience,
                    "distance": float(c.dist),
                })
                visited.add(c.id)

        if len(cluster) >= 2:
            clusters.append(cluster)
        if len(clusters) >= max_clusters:
            break

    return clusters


async def get_promote_candidates(
    session: AsyncSession,
    min_use_count: int = 5,
    min_confidence: int = 3,
    min_salience: int = 3,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Archival facts that meet the promotion threshold."""
    rows = (await session.execute(text(
        "SELECT id, content, tags, confidence, stability, salience, use_count, last_used_at "
        "FROM archival_facts_staging "
        "WHERE is_deleted = FALSE "
        "AND use_count >= :uc AND confidence >= :conf "
        "AND stability = 'long_term' AND salience >= :salience "
        "ORDER BY use_count DESC LIMIT :lim"
    ), {
        "uc": min_use_count,
        "conf": min_confidence,
        "salience": min_salience,
        "lim": limit,
    })).all()

    return [
        {
            "id": r.id,
            "content": r.content,
            "tags": list(r.tags or []),
            "confidence": r.confidence,
            "stability": r.stability,
            "salience": r.salience,
            "use_count": r.use_count,
        }
        for r in rows
    ]


async def get_stale_candidates(
    session: AsyncSession,
    days: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (await session.execute(text(
        "SELECT id, content, confidence, stability, salience, last_used_at, created_at "
        "FROM archival_facts_staging "
        "WHERE is_deleted = FALSE "
        "AND (confidence <= 1 OR stability = 'temporary' OR salience <= 1) "
        "AND (last_used_at IS NULL OR last_used_at < :cutoff) "
        "ORDER BY created_at ASC LIMIT :lim"
    ), {"cutoff": cutoff, "lim": limit})).all()

    return [
        {
            "id": r.id,
            "content": r.content,
            "confidence": r.confidence,
            "stability": r.stability,
            "salience": r.salience,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        }
        for r in rows
    ]


async def get_core_refresh_context(
    session: AsyncSession,
    archival_limit: int = 30,
    ops_limit: int = 20,
) -> dict[str, Any]:
    """Load staging core + supporting evidence for core refresh."""
    core_rows = (await session.execute(text(
        "SELECT label, value, version, char_limit "
        "FROM core_blocks_staging ORDER BY label"
    ))).all()
    archival_rows = (await session.execute(text(
        "SELECT id, content, tags, confidence, stability, salience, use_count, "
        "last_used_at, created_at "
        "FROM archival_facts_staging "
        "WHERE is_deleted = FALSE "
        "ORDER BY salience DESC, confidence DESC, use_count DESC, id DESC "
        "LIMIT :lim"
    ), {"lim": archival_limit})).all()
    op_rows = (await session.execute(text(
        "SELECT op_type, actor, target_kind, target_id, reason, ts "
        "FROM memory_ops_log ORDER BY ts DESC, id DESC LIMIT :lim"
    ), {"lim": ops_limit})).all()

    return {
        "core_blocks": [
            {
                "label": r.label,
                "value": r.value,
                "version": r.version,
                "char_limit": r.char_limit,
            }
            for r in core_rows
        ],
        "supporting_archival": [
            {
                "id": r.id,
                "content": r.content,
                "tags": list(r.tags or []),
                "confidence": r.confidence,
                "stability": r.stability,
                "salience": r.salience,
                "use_count": r.use_count,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in archival_rows
        ],
        "recent_ops": [
            {
                "op_type": r.op_type,
                "actor": r.actor,
                "target_kind": r.target_kind,
                "target_id": r.target_id,
                "reason": r.reason,
                "ts": r.ts.isoformat() if r.ts else None,
            }
            for r in op_rows
        ],
    }


# =====================================================================
# Write-side: apply LLM decisions to staging tables
# =====================================================================


async def apply_consolidation(
    session: AsyncSession,
    actions: list[dict[str, Any]],
) -> list[MemoryOpDraft]:
    """Apply LLM-decided MERGE actions to staging."""
    pending_ops: list[MemoryOpDraft] = []
    for act in actions:
        if act.get("decision") != "MERGE":
            continue
        kept_id = act["kept_id"]
        discarded_ids = act["discarded_ids"]
        merged_content = act["merged_content"]
        reason = act.get("reason", "")

        # Update the kept row's content.
        await session.execute(text(
            "UPDATE archival_facts_staging "
            "SET content = :content WHERE id = :kid"
        ), {"content": merged_content, "kid": kept_id})

        # Mark discarded as deleted.
        if discarded_ids:
            await session.execute(text(
                "UPDATE archival_facts_staging "
                "SET is_deleted = TRUE WHERE id = ANY(:ids)"
            ), {"ids": discarded_ids})

        pending_ops.append({
            "op_type": "sleep_consolidate",
            "actor": SLEEP_ACTOR,
            "target_kind": "archival",
            "target_id": str(kept_id),
            "before_value": None,
            "after_value": merged_content,
            "reason": f"Merged {len(discarded_ids)} duplicates; {reason}",
        })
    await session.commit()
    return pending_ops


async def apply_promotions(
    session: AsyncSession,
    actions: list[dict[str, Any]],
) -> list[MemoryOpDraft]:
    """Apply LLM-decided PROMOTE actions to core_blocks_staging."""
    pending_ops: list[MemoryOpDraft] = []
    for act in actions:
        if act.get("decision") != "PROMOTE":
            continue
        target = act["target_block"]
        new_value = act["new_block_value"]
        reason = act.get("reason", "")
        fact_id = act["fact_id"]

        # Read current value for log.
        cur = (await session.execute(text(
            "SELECT value FROM core_blocks_staging WHERE label = :l"
        ), {"l": target})).scalar_one_or_none()

        await session.execute(text(
            "UPDATE core_blocks_staging "
            "SET value = :v, version = version + 1, "
            "last_writer = 'sleep_agent', updated_at = now() "
            "WHERE label = :l"
        ), {"v": new_value, "l": target})

        pending_ops.append({
            "op_type": "sleep_promote",
            "actor": SLEEP_ACTOR,
            "target_kind": "core",
            "target_id": target,
            "before_value": cur,
            "after_value": new_value,
            "reason": f"Promoted from archival id={fact_id}: {reason}",
        })
    await session.commit()
    return pending_ops


async def apply_demotions(
    session: AsyncSession,
    actions: list[dict[str, Any]],
) -> list[MemoryOpDraft]:
    """Soft-delete stale archival in staging."""
    pending_ops: list[MemoryOpDraft] = []
    for act in actions:
        if act.get("decision") != "FORGET":
            continue
        fact_id = act["fact_id"]
        reason = act.get("reason", "")

        cur = (await session.execute(text(
            "SELECT content FROM archival_facts_staging WHERE id = :i"
        ), {"i": fact_id})).scalar_one_or_none()

        await session.execute(text(
            "UPDATE archival_facts_staging "
            "SET is_deleted = TRUE WHERE id = :i"
        ), {"i": fact_id})

        pending_ops.append({
            "op_type": "sleep_demote",
            "actor": SLEEP_ACTOR,
            "target_kind": "archival",
            "target_id": str(fact_id),
            "before_value": cur,
            "after_value": None,
            "reason": reason,
        })
    await session.commit()
    return pending_ops


async def apply_resolutions(
    session: AsyncSession,
    contradictions: list[dict[str, Any]],
) -> list[MemoryOpDraft]:
    """Apply LLM-decided contradiction fixes to core_blocks_staging."""
    pending_ops: list[MemoryOpDraft] = []
    for c in contradictions:
        block = c["fix_block"]
        new_value = c["new_block_value"]
        reason = c.get("reason", "")

        cur = (await session.execute(text(
            "SELECT value FROM core_blocks_staging WHERE label = :l"
        ), {"l": block})).scalar_one_or_none()

        await session.execute(text(
            "UPDATE core_blocks_staging "
            "SET value = :v, version = version + 1, "
            "last_writer = 'sleep_agent', updated_at = now() "
            "WHERE label = :l"
        ), {"v": new_value, "l": block})

        pending_ops.append({
            "op_type": "sleep_resolve",
            "actor": SLEEP_ACTOR,
            "target_kind": "core",
            "target_id": block,
            "before_value": cur,
            "after_value": new_value,
            "reason": f"Resolved contradiction: {reason}",
        })
    await session.commit()
    return pending_ops


async def apply_core_refreshes(
    session: AsyncSession,
    actions: list[dict[str, Any]],
) -> list[MemoryOpDraft]:
    """Apply LLM-decided core refreshes to core_blocks_staging."""
    pending_ops: list[MemoryOpDraft] = []
    for act in actions:
        if act.get("decision") != "REFRESH":
            continue
        block = act["block"]
        new_value = act["new_block_value"]
        reason = act.get("reason", "")

        cur = (await session.execute(text(
            "SELECT value FROM core_blocks_staging WHERE label = :l"
        ), {"l": block})).scalar_one_or_none()

        if cur == new_value:
            continue

        await session.execute(text(
            "UPDATE core_blocks_staging "
            "SET value = :v, version = version + 1, "
            "last_writer = 'sleep_agent', updated_at = now() "
            "WHERE label = :l"
        ), {"v": new_value, "l": block})

        pending_ops.append({
            "op_type": "sleep_core_refresh",
            "actor": SLEEP_ACTOR,
            "target_kind": "core",
            "target_id": block,
            "before_value": cur,
            "after_value": new_value,
            "reason": f"Refreshed core block: {reason}",
        })
    await session.commit()
    return pending_ops


def draft_reflection_log(text_value: str) -> MemoryOpDraft:
    """Build the REFLECT phase audit log draft."""
    return {
        "op_type": "sleep_reflect",
        "actor": SLEEP_ACTOR,
        "target_kind": None,
        "target_id": None,
        "before_value": None,
        "after_value": text_value,
        "reason": "periodic reflection snapshot",
    }


# =====================================================================
# helpers
# =====================================================================


def _row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "content": r.content,
        "tags": list(r.tags or []),
        "confidence": r.confidence,
        "stability": r.stability,
        "salience": r.salience,
        "distance": 0.0,
    }
