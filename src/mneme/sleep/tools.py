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

from mneme.llm.client import embed_text
from mneme.memory.store import Actor, MemoryOpDraft

SLEEP_ACTOR: Actor = "sleep_agent"
CORE_REFRESH_CHECKPOINT_TARGET = "__checkpoint__"
_CORE_REFRESH_RELEVANT_OPS = (
    "remember",
    "forget",
    "sleep_consolidate",
    "sleep_promote",
    "sleep_demote",
    "sleep_resolve",
    "sleep_core_refresh",
)


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
    current_cycle_ops: list[MemoryOpDraft] | None = None,
    all_facts_threshold: int = 200,
    per_block_limit: int = 8,
    high_signal_limit: int = 10,
) -> dict[str, Any]:
    """Load incremental, block-aware evidence for core refresh.

    Small memories are loaded in full. Above the threshold, evidence is the
    union of facts changed since the last successful refresh check, semantic
    top-K matches for every non-empty core block, and global high-signal facts.
    """
    core_rows = (await session.execute(text(
        "SELECT label, value, version, char_limit "
        "FROM core_blocks_staging ORDER BY label"
    ))).all()
    core_blocks = [
        {
            "label": r.label,
            "value": r.value,
            "version": r.version,
            "char_limit": r.char_limit,
        }
        for r in core_rows
    ]
    non_empty_cores = [
        block for block in core_blocks if (block.get("value") or "").strip()
    ]

    active_count = int((await session.execute(text(
        "SELECT count(*) FROM archival_facts_staging WHERE is_deleted = FALSE"
    ))).scalar_one())
    checkpoint_id = (await session.execute(text(
        "SELECT max(id) FROM memory_ops_log "
        "WHERE op_type = 'sleep_core_refresh' AND target_id = :target"
    ), {"target": CORE_REFRESH_CHECKPOINT_TARGET})).scalar_one()
    checkpoint_value = int(checkpoint_id) if checkpoint_id is not None else None

    op_rows = (await session.execute(text(
        "SELECT id, op_type, actor, target_kind, target_id, reason, ts "
        "FROM memory_ops_log "
        "WHERE id > :checkpoint "
        "AND op_type = ANY(:op_types) "
        "AND NOT (op_type = 'sleep_core_refresh' AND target_id = :target) "
        "ORDER BY id ASC"
    ), {
        "checkpoint": checkpoint_value or 0,
        "op_types": list(_CORE_REFRESH_RELEVANT_OPS),
        "target": CORE_REFRESH_CHECKPOINT_TARGET,
    })).all()

    pending_relevant = [
        op for op in current_cycle_ops or []
        if op.get("op_type") in _CORE_REFRESH_RELEVANT_OPS
        and op.get("target_id") != CORE_REFRESH_CHECKPOINT_TARGET
    ]
    ops_since_refresh = [
        {
            "id": r.id,
            "op_type": r.op_type,
            "actor": r.actor,
            "target_kind": r.target_kind,
            "target_id": r.target_id,
            "reason": r.reason,
            "ts": r.ts.isoformat() if r.ts else None,
            "source": "committed",
        }
        for r in op_rows
    ]
    ops_since_refresh.extend(
        {
            "id": None,
            "op_type": op.get("op_type"),
            "actor": op.get("actor"),
            "target_kind": op.get("target_kind"),
            "target_id": op.get("target_id"),
            "reason": op.get("reason"),
            "ts": None,
            "source": "current_cycle_pending",
        }
        for op in pending_relevant
    )

    if not non_empty_cores:
        return {
            "refresh_required": False,
            "skip_reason": "no_non_empty_core",
            "evidence_mode": "none",
            "checkpoint_op_id": checkpoint_value,
            "active_archival_count": active_count,
            "core_blocks": core_blocks,
            "supporting_archival": [],
            "ops_since_last_refresh": ops_since_refresh,
        }

    first_check = checkpoint_value is None
    if not first_check and not ops_since_refresh:
        return {
            "refresh_required": False,
            "skip_reason": "no_relevant_changes_since_checkpoint",
            "evidence_mode": "none",
            "checkpoint_op_id": checkpoint_value,
            "active_archival_count": active_count,
            "core_blocks": core_blocks,
            "supporting_archival": [],
            "ops_since_last_refresh": [],
        }

    facts_by_id: dict[int, dict[str, Any]] = {}
    changed_ids = {
        int(op["target_id"])
        for op in ops_since_refresh
        if op.get("target_kind") == "archival"
        and str(op.get("target_id") or "").isdigit()
    }

    def add_fact(row: Any, reason: str, distance: float | None = None) -> None:
        fact = facts_by_id.setdefault(row.id, _refresh_fact_to_dict(row))
        reasons = fact.setdefault("evidence_reasons", [])
        if reason not in reasons:
            reasons.append(reason)
        if distance is not None:
            distances = fact.setdefault("semantic_distances", {})
            distances[reason.removeprefix("semantic:")] = distance

    if active_count <= all_facts_threshold:
        evidence_mode = "all_active"
        archival_rows = (await session.execute(text(
            "SELECT id, content, tags, confidence, stability, salience, use_count, "
            "last_used_at, created_at, is_deleted "
            "FROM archival_facts_staging WHERE is_deleted = FALSE ORDER BY id ASC"
        ))).all()
        for row in archival_rows:
            add_fact(row, "all_active")
    else:
        evidence_mode = "adaptive"
        high_signal_rows = (await session.execute(text(
            "SELECT id, content, tags, confidence, stability, salience, use_count, "
            "last_used_at, created_at, is_deleted "
            "FROM archival_facts_staging "
            "WHERE is_deleted = FALSE AND confidence = 3 "
            "AND stability = 'long_term' AND salience = 3 "
            "ORDER BY use_count DESC, id DESC LIMIT :lim"
        ), {"lim": high_signal_limit})).all()
        for row in high_signal_rows:
            add_fact(row, "global_high_signal")

        for block in non_empty_cores:
            vector = await embed_text(
                f"Core block {block['label']}: {block['value']}"
            )
            semantic_rows = (await session.execute(text(
                "SELECT id, content, tags, confidence, stability, salience, "
                "use_count, last_used_at, created_at, is_deleted, "
                "embedding <=> CAST(:embedding AS vector) AS distance "
                "FROM archival_facts_staging "
                "WHERE is_deleted = FALSE AND embedding IS NOT NULL "
                "ORDER BY distance LIMIT :lim"
            ), {
                "embedding": _vector_literal(vector),
                "lim": per_block_limit,
            })).all()
            for row in semantic_rows:
                add_fact(
                    row,
                    f"semantic:{block['label']}",
                    float(row.distance),
                )

    # Current-cycle Awake writes can commit after the snapshot. Such rows are
    # absent or stale in staging until atomic_swap(), so read both versions now.
    # This prevents advancing the refresh checkpoint past unseen changes.
    if changed_ids:
        changed_staging_rows = (await session.execute(text(
            "SELECT id, content, tags, confidence, stability, salience, use_count, "
            "last_used_at, created_at, is_deleted "
            "FROM archival_facts_staging WHERE id = ANY(:ids)"
        ), {"ids": sorted(changed_ids)})).all()
        for row in changed_staging_rows:
            add_fact(row, "changed_since_refresh")

        changed_main_rows = (await session.execute(text(
            "SELECT id, content, tags, confidence, stability, salience, use_count, "
            "last_used_at, created_at, is_deleted "
            "FROM archival_facts WHERE id = ANY(:ids)"
        ), {"ids": sorted(changed_ids)})).all()
        for row in changed_main_rows:
            add_fact(row, "changed_since_refresh")
            fact = facts_by_id[row.id]
            fact["use_count"] = max(int(fact["use_count"]), int(row.use_count))
            fact["last_used_at"] = _latest_iso_datetime(
                fact.get("last_used_at"),
                row.last_used_at.isoformat() if row.last_used_at else None,
            )
            fact["is_deleted"] = bool(fact["is_deleted"] or row.is_deleted)

    return {
        "refresh_required": True,
        "skip_reason": None,
        "evidence_mode": evidence_mode,
        "checkpoint_op_id": checkpoint_value,
        "active_archival_count": active_count,
        "core_blocks": core_blocks,
        "supporting_archival": list(facts_by_id.values()),
        "ops_since_last_refresh": ops_since_refresh,
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


def draft_core_refresh_checkpoint(
    context: dict[str, Any],
    actions: list[dict[str, Any]],
) -> MemoryOpDraft:
    """Mark the evidence cursor only after the enclosing swap commits."""
    refreshed = sum(
        1 for action in actions if action.get("decision") == "REFRESH"
    )
    return {
        "op_type": "sleep_core_refresh",
        "actor": SLEEP_ACTOR,
        "target_kind": "core",
        "target_id": CORE_REFRESH_CHECKPOINT_TARGET,
        "before_value": None,
        "after_value": None,
        "reason": (
            "Core refresh check completed; "
            f"mode={context.get('evidence_mode')}; "
            f"active_facts={context.get('active_archival_count', 0)}; "
            f"evidence_facts={len(context.get('supporting_archival', []))}; "
            f"changed_ops={len(context.get('ops_since_last_refresh', []))}; "
            f"refreshed_blocks={refreshed}"
        ),
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


def _refresh_fact_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "content": row.content,
        "tags": list(row.tags or []),
        "confidence": row.confidence,
        "stability": row.stability,
        "salience": row.salience,
        "use_count": row.use_count,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_deleted": row.is_deleted,
    }


def _latest_iso_datetime(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()
