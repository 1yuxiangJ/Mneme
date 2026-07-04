"""Staging snapshot + atomic swap for Sleep agent.

Concurrency model (Letta-paper-inspired, MVP-simplified):

  1. snapshot_to_staging()
     - DROP + CREATE  *_staging  (LIKE main INCLUDING ALL)
     - INSERT INTO   *_staging   SELECT * FROM main
     - Records snapshot_ts.

  2. Sleep agent works only on `*_staging` tables.

  3. atomic_swap()
     - In a single transaction:
         a) Move any new archival rows from main → staging
            (created_at > snapshot_ts, skip if already present)
         b) RENAME the three pairs to swap main ↔ staging
         c) Truncate the now-staging (old main).
     - Awake's next read picks up the new main.

Trade-off (MVP): If Awake INSERTED to archival_facts during the cycle,
those rows are merged in step (a). If Awake UPDATED (e.g. mark_archival_used),
those updates may be lost on rows that Sleep also modified. We accept this for
MVP; the conflict is rare (Sleep modifies few rows; Awake updates many).

Day 03+ improvement: row-level merge for use_count / last_used_at.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.config import settings

# Tables that participate in staging.
_STAGED_TABLES = ("core_blocks", "archival_facts")
_ARCHIVAL_ID_SEQUENCE = "archival_facts_id_seq"


async def _set_archival_id_default(session: AsyncSession, table_name: str) -> None:
    await session.execute(text(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN id SET DEFAULT nextval('{_ARCHIVAL_ID_SEQUENCE}'::regclass)
        """
    ))


async def _ensure_archival_id_sequence(session: AsyncSession) -> None:
    """Ensure archival_facts.id has a stable sequence across table swaps.

    `CREATE TABLE ... LIKE ... INCLUDING ALL` plus rename-based swaps can leave
    the live table without the original BIGSERIAL default in older local DBs.
    Sleep must repair that before creating staging, otherwise snapshot fails
    before any ops_log entry can be written.
    """
    await session.execute(text(
        f"CREATE SEQUENCE IF NOT EXISTS {_ARCHIVAL_ID_SEQUENCE}"
    ))
    await session.execute(text(
        f"""
        SELECT setval(
            '{_ARCHIVAL_ID_SEQUENCE}',
            GREATEST((SELECT COALESCE(MAX(id), 0) FROM archival_facts), 1),
            true
        )
        """
    ))
    await _set_archival_id_default(session, "archival_facts")


async def snapshot_to_staging(session: AsyncSession) -> datetime:
    """Snapshot the main tables into *_staging counterparts.

    Drops + recreates the staging tables (idempotent).

    Returns the snapshot timestamp (used by atomic_swap to merge newer rows).
    """
    snapshot_ts = datetime.now(UTC)

    await _ensure_archival_id_sequence(session)

    for tbl in _STAGED_TABLES:
        staging = f"{tbl}_staging"
        await session.execute(text(f"DROP TABLE IF EXISTS {staging} CASCADE"))
        await session.execute(
            text(f"CREATE TABLE {staging} (LIKE {tbl} INCLUDING ALL)")
        )
        if tbl == "archival_facts":
            await _set_archival_id_default(session, "archival_facts_staging")
        await session.execute(
            text(f"INSERT INTO {staging} SELECT * FROM {tbl}")
        )

    await session.commit()
    return snapshot_ts


async def atomic_swap(session: AsyncSession, snapshot_ts: datetime) -> None:
    """Atomically swap staging ↔ main.

    Args:
        snapshot_ts: timestamp returned by snapshot_to_staging().
    """
    # All of this in one transaction.
    await session.execute(
        text("SELECT set_config('lock_timeout', :lock_timeout, true)"),
        {"lock_timeout": f"{settings.sleep_swap_lock_timeout_ms}ms"},
    )

    # Step a: merge new archival rows from main → staging (Sleep didn't see them).
    await session.execute(text(
        """
        INSERT INTO archival_facts_staging
            SELECT * FROM archival_facts
            WHERE created_at > :snapshot_ts
        ON CONFLICT (id) DO NOTHING
        """
    ), {"snapshot_ts": snapshot_ts})

    # Step b: swap names using a tmp suffix.
    # Use double rename via tmp to ensure atomicity within the transaction.
    for tbl in _STAGED_TABLES:
        staging = f"{tbl}_staging"
        tmp = f"{tbl}_tmp_swap"
        await session.execute(text(f"ALTER TABLE {tbl} RENAME TO {tmp}"))
        await session.execute(text(f"ALTER TABLE {staging} RENAME TO {tbl}"))
        await session.execute(text(f"ALTER TABLE {tmp} RENAME TO {staging}"))

    # Step c: truncate the now-staging (which was the old main).
    for tbl in _STAGED_TABLES:
        staging = f"{tbl}_staging"
        await session.execute(text(f"TRUNCATE {staging}"))

    await session.commit()


async def cleanup_staging(session: AsyncSession) -> None:
    """Drop staging tables (after successful swap or if cycle aborted)."""
    for tbl in _STAGED_TABLES:
        await session.execute(text(f"DROP TABLE IF EXISTS {tbl}_staging CASCADE"))
    await session.commit()
