"""Memory store: CRUD + semantic search.

Access policy (Letta read-only primary):
  awake_agent   → read core_blocks; read/write archival_facts
  sleep_agent   → full write on both (sole writer of core_blocks)

`actor` is passed explicitly by callers. Non-sleep actors attempting to
write core_blocks are rejected and logged as `policy_violation`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mneme.db.models import (
    ArchivalFact,
    CoreBlock,
    MemoryOpsLog,
    get_sessionmaker,
)
from mneme.llm.client import embed_text

Actor = Literal["awake_agent", "sleep_agent"]
OpType = Literal[
    "remember",
    "recall",
    "forget",
    "sleep_consolidate",
    "sleep_promote",
    "sleep_demote",
    "sleep_resolve",
    "sleep_reflect",
    "policy_violation",
]


# -------------------------------------------------------------
# Read-only result dataclasses
# -------------------------------------------------------------


@dataclass
class ArchivalSearchResult:
    id: int
    content: str
    tags: list[str]
    confidence: int
    distance: float  # cosine distance; lower = closer
    created_at: datetime


@dataclass
class CoreBlockSnapshot:
    label: str
    value: str
    char_limit: int
    version: int
    updated_at: datetime


@dataclass
class MemoryOverview:
    core_blocks: list[CoreBlockSnapshot]
    archival_count: int


# -------------------------------------------------------------
# Read-side helpers (used by both Awake and Sleep)
# -------------------------------------------------------------


async def list_core_blocks(session: AsyncSession) -> list[CoreBlockSnapshot]:
    res = await session.execute(select(CoreBlock).order_by(CoreBlock.label))
    return [
        CoreBlockSnapshot(
            label=b.label,
            value=b.value,
            char_limit=b.char_limit,
            version=b.version,
            updated_at=b.updated_at,
        )
        for b in res.scalars()
    ]


async def count_archival(session: AsyncSession, include_deleted: bool = False) -> int:
    stmt = select(func.count(ArchivalFact.id))
    if not include_deleted:
        stmt = stmt.where(ArchivalFact.is_deleted.is_(False))
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def get_memory_overview(session: AsyncSession) -> MemoryOverview:
    return MemoryOverview(
        core_blocks=await list_core_blocks(session),
        archival_count=await count_archival(session),
    )


async def semantic_search_archival(
    session: AsyncSession,
    query: str,
    limit: int = 5,
) -> list[ArchivalSearchResult]:
    """Vector search over archival_facts (cosine distance)."""
    vec = await embed_text(query)
    stmt = (
        select(
            ArchivalFact,
            ArchivalFact.embedding.cosine_distance(vec).label("distance"),
        )
        .where(ArchivalFact.is_deleted.is_(False))
        .where(ArchivalFact.embedding.is_not(None))
        .order_by("distance")
        .limit(limit)
    )
    res = await session.execute(stmt)
    rows = res.all()
    return [
        ArchivalSearchResult(
            id=row.ArchivalFact.id,
            content=row.ArchivalFact.content,
            tags=list(row.ArchivalFact.tags or []),
            confidence=row.ArchivalFact.confidence,
            distance=float(row.distance),
            created_at=row.ArchivalFact.created_at,
        )
        for row in rows
    ]


# -------------------------------------------------------------
# Write-side: archival (Awake + Sleep)
# -------------------------------------------------------------


async def insert_archival(
    session: AsyncSession,
    content: str,
    tags: list[str] | None,
    confidence: int,
    source: str | None,
    actor: Actor,
    reason: str | None = None,
    op_type: OpType | None = None,
) -> int:
    """Insert a new archival fact + log to memory_ops_log.

    op_type defaults to 'remember' for Awake and 'sleep_consolidate' for Sleep.
    """
    vec = await embed_text(content)
    fact = ArchivalFact(
        content=content,
        tags=tags,
        confidence=confidence,
        source=source,
        embedding=vec,
    )
    session.add(fact)
    await session.flush()  # populate fact.id

    if op_type is None:
        op_type = "remember" if actor == "awake_agent" else "sleep_consolidate"

    session.add(MemoryOpsLog(
        op_type=op_type,
        actor=actor,
        target_kind="archival",
        target_id=str(fact.id),
        before_value=None,
        after_value=content,
        reason=reason,
    ))
    await session.commit()
    return fact.id


async def soft_delete_archival(
    session: AsyncSession,
    fact_id: int,
    reason: str,
    actor: Actor,
    op_type: OpType | None = None,
) -> None:
    """Mark archival fact as deleted (soft) + log."""
    fact = await session.get(ArchivalFact, fact_id)
    if fact is None or fact.is_deleted:
        return
    before_value = fact.content
    fact.is_deleted = True

    if op_type is None:
        op_type = "forget" if actor == "awake_agent" else "sleep_demote"

    session.add(MemoryOpsLog(
        op_type=op_type,
        actor=actor,
        target_kind="archival",
        target_id=str(fact_id),
        before_value=before_value,
        after_value=None,
        reason=reason,
    ))
    await session.commit()


async def mark_archival_used(session: AsyncSession, fact_ids: list[int]) -> None:
    """Bump use_count + last_used_at for recalled facts. No log (hot path)."""
    if not fact_ids:
        return
    stmt = (
        update(ArchivalFact)
        .where(ArchivalFact.id.in_(fact_ids))
        .values(
            use_count=ArchivalFact.use_count + 1,
            last_used_at=func.now(),
        )
    )
    await session.execute(stmt)
    await session.commit()


# -------------------------------------------------------------
# Write-side: core_blocks (SLEEP ONLY)
# -------------------------------------------------------------


async def write_core_block(
    session: AsyncSession,
    label: str,
    new_value: str,
    actor: Actor,
    reason: str,
    op_type: OpType = "sleep_promote",
) -> None:
    """Update a core block (full overwrite).

    POLICY: actor MUST be 'sleep_agent'. Awake attempts are logged as
    'policy_violation' and PermissionError is raised.
    """
    if actor != "sleep_agent":
        session.add(MemoryOpsLog(
            op_type="policy_violation",
            actor=actor,
            target_kind="core",
            target_id=label,
            before_value=None,
            after_value=new_value,
            reason=f"Non-sleep actor attempted to write core_block ({reason})",
        ))
        await session.commit()
        raise PermissionError(
            f"Actor '{actor}' is not allowed to write core_blocks; "
            "only 'sleep_agent' is."
        )

    block = await session.get(CoreBlock, label)
    if block is None:
        raise ValueError(f"Unknown core block label: {label}")
    before_value = block.value
    block.value = new_value
    block.version += 1
    block.last_writer = actor
    block.updated_at = datetime.now(UTC)

    session.add(MemoryOpsLog(
        op_type=op_type,
        actor=actor,
        target_kind="core",
        target_id=label,
        before_value=before_value,
        after_value=new_value,
        reason=reason,
    ))
    await session.commit()


# -------------------------------------------------------------
# Convenience
# -------------------------------------------------------------


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory."""
    return get_sessionmaker()
