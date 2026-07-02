"""Demo memory seeding utilities.

This module is intentionally explicit: it inserts demo-tagged archival facts
only when the caller passes a confirmation flag from the script. The seeded
facts are useful for rehearsing Sleep promote/consolidate behavior before enough
real dogfooding data has accumulated.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, TypedDict

from sqlalchemy import select

from mneme.db.models import ArchivalFact
from mneme.memory.store import (
    insert_archival,
    session_factory,
    soft_delete_archival,
)


class DemoFact(TypedDict):
    content: str
    tags: list[str]
    confidence: int


DEMO_FACTS: list[DemoFact] = [
    {
        "content": (
            "User is a Java backend developer preparing for internships "
            "and campus recruiting."
        ),
        "tags": ["demo-seed", "career", "backend"],
        "confidence": 3,
    },
    {
        "content": "User is building Mneme as an agent infrastructure resume project.",
        "tags": ["demo-seed", "project", "agent"],
        "confidence": 3,
    },
    {
        "content": "User prefers direct, concrete, engineering-oriented Chinese explanations.",
        "tags": ["demo-seed", "communication", "preference"],
        "confidence": 3,
    },
    {
        "content": "User dislikes vague questions and empty high-level phrasing.",
        "tags": ["demo-seed", "communication", "preference"],
        "confidence": 3,
    },
    {
        "content": "User wants agent projects to show real engineering value, not feel like toys.",
        "tags": ["demo-seed", "product", "preference"],
        "confidence": 3,
    },
    {
        "content": "User is interested in long-term memory agents inspired by Letta.",
        "tags": ["demo-seed", "agent", "memory"],
        "confidence": 3,
    },
    {
        "content": "User named the project Mneme after considering memory-related names.",
        "tags": ["demo-seed", "project", "naming"],
        "confidence": 2,
    },
    {
        "content": "User prefers Java backend framing when explaining engineering trade-offs.",
        "tags": ["demo-seed", "backend", "communication"],
        "confidence": 2,
    },
    {
        "content": "User wants GitHub commits pushed periodically during project construction.",
        "tags": ["demo-seed", "workflow", "github"],
        "confidence": 2,
    },
    {
        "content": (
            "User wants final verification tasks grouped at the end instead "
            "of interrupting development."
        ),
        "tags": ["demo-seed", "workflow", "preference"],
        "confidence": 3,
    },
    {
        "content": "User uses DataGrip to inspect the local PostgreSQL database.",
        "tags": ["demo-seed", "tooling", "database"],
        "confidence": 2,
    },
    {
        "content": "User's local Mneme project lives at /Users/mac/dream.",
        "tags": ["demo-seed", "environment", "mneme"],
        "confidence": 3,
    },
]


async def seed_demo_memory() -> dict[str, Any]:
    """Insert demo facts that are not already present."""
    session_maker = session_factory()
    inserted: list[int] = []
    skipped: list[str] = []

    async with session_maker() as session:
        existing_contents = set(
            (
                await session.execute(
                    select(ArchivalFact.content).where(
                        ArchivalFact.is_deleted.is_(False)
                    )
                )
            ).scalars()
        )

    for fact in DEMO_FACTS:
        if fact["content"] in existing_contents:
            skipped.append(fact["content"])
            continue
        async with session_maker() as session:
            fact_id = await insert_archival(
                session,
                content=fact["content"],
                tags=fact["tags"],
                confidence=fact["confidence"],
                source="demo-seed",
                actor="awake_agent",
                reason="Seeded demo memory for Sleep promote/consolidate rehearsal.",
            )
            inserted.append(fact_id)

    return {
        "status": "ok",
        "mode": "seed",
        "inserted_count": len(inserted),
        "inserted_ids": inserted,
        "skipped_existing_count": len(skipped),
    }


async def cleanup_demo_memory() -> dict[str, Any]:
    """Soft-delete active demo-seeded facts."""
    session_maker = session_factory()
    async with session_maker() as session:
        rows = (
            await session.execute(
                select(ArchivalFact.id)
                .where(ArchivalFact.source == "demo-seed")
                .where(ArchivalFact.is_deleted.is_(False))
                .order_by(ArchivalFact.id)
            )
        ).scalars()
        fact_ids = list(rows)

    deleted: list[int] = []
    for fact_id in fact_ids:
        async with session_maker() as session:
            await soft_delete_archival(
                session,
                fact_id,
                reason="Cleanup demo-seeded Mneme memory.",
                actor="awake_agent",
            )
            deleted.append(fact_id)

    return {
        "status": "ok",
        "mode": "cleanup",
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo-tagged Mneme memories.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Soft-delete active demo-seeded facts instead of inserting them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that demo facts should be inserted or cleaned up.",
    )
    args = parser.parse_args()
    if not args.yes:
        print("Refusing to mutate demo memory without --yes.")
        return 2

    result = asyncio.run(
        cleanup_demo_memory() if args.cleanup else seed_demo_memory()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
