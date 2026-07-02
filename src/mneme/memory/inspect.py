"""Read-only memory inspection helpers for local debugging."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from mneme.db.models import ArchivalFact, CoreBlock, MemoryOpsLog, get_sessionmaker


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def collect_snapshot(limit: int = 10) -> dict[str, Any]:
    """Collect a small read-only snapshot of current memory state."""
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        core_rows = (
            await session.execute(select(CoreBlock).order_by(CoreBlock.label))
        ).scalars()
        archival_rows = (
            await session.execute(
                select(ArchivalFact)
                .where(ArchivalFact.is_deleted.is_(False))
                .order_by(ArchivalFact.id.desc())
                .limit(limit)
            )
        ).scalars()
        op_rows = (
            await session.execute(
                select(MemoryOpsLog)
                .order_by(MemoryOpsLog.ts.desc(), MemoryOpsLog.id.desc())
                .limit(limit)
            )
        ).scalars()

        return {
            "core_blocks": [
                {
                    "label": row.label,
                    "value": row.value,
                    "version": row.version,
                    "last_writer": row.last_writer,
                    "updated_at": _dt(row.updated_at),
                }
                for row in core_rows
            ],
            "archival_facts": [
                {
                    "id": row.id,
                    "content": row.content,
                    "tags": row.tags or [],
                    "confidence": row.confidence,
                    "source": row.source,
                    "use_count": row.use_count,
                    "created_at": _dt(row.created_at),
                    "last_used_at": _dt(row.last_used_at),
                }
                for row in archival_rows
            ],
            "recent_ops": [
                {
                    "id": row.id,
                    "op_type": row.op_type,
                    "actor": row.actor,
                    "target_kind": row.target_kind,
                    "target_id": row.target_id,
                    "reason": row.reason,
                    "ts": _dt(row.ts),
                }
                for row in op_rows
            ],
        }


def format_snapshot(snapshot: dict[str, Any]) -> str:
    """Format a snapshot as stable JSON for terminal output."""
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)


async def run(limit: int = 10) -> int:
    snapshot = await collect_snapshot(limit=limit)
    print(format_snapshot(snapshot))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Mneme memory tables.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum archival facts and recent ops to print.",
    )
    args = parser.parse_args()
    return asyncio.run(run(limit=args.limit))
