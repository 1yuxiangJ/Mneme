"""LangGraph @tool definitions for the Awake agent.

These wrap mneme.memory.store CRUD with awake_agent actor.

Mapping from MCP-exposed tools (mcp_server.py) → internal tools:
  MCP `remember`     → search_archival (dedup) + insert_archival
  MCP `recall`       → load_core (context) + search_archival
  MCP `list_memory`  → get_overview
  MCP `forget`       → forget_archival

The Awake agent's ReAct loop chooses which internal tools to call.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from mneme.memory.store import (
    Actor,
    get_memory_overview,
    insert_archival,
    list_core_blocks,
    mark_archival_used,
    semantic_search_archival,
    session_factory,
    soft_delete_archival,
)

AWAKE_ACTOR: Actor = "awake_agent"


@tool
async def load_core() -> dict[str, Any]:
    """Load all core blocks (the user's structured profile).

    Use this to remind yourself who the user is before deciding what to do.
    Returns 5 blocks: background, preferences, habits, skills, lessons_learned.
    """
    session_maker = session_factory()
    async with session_maker() as session:
        blocks = await list_core_blocks(session)
    return {
        "blocks": [
            {"label": b.label, "value": b.value, "version": b.version}
            for b in blocks
        ]
    }


@tool
async def search_archival(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantic search over archival facts (user's free-form memory).

    Args:
        query: Natural-language query.
        limit: Max results (default 5).

    Returns matching facts with cosine distance.
    Side-effect: increments use_count for returned facts.
    """
    results = await _search_archival(query, limit, track_usage=True)
    return {"results": results}


@tool
async def find_archival_duplicates(query: str, limit: int = 5) -> dict[str, Any]:
    """Search for near-duplicate archival facts without counting a user recall.

    Use only during Remember deduplication. Unlike search_archival, this does
    not increment use_count or last_used_at, because an internal write-time
    duplicate check is not evidence that the memory helped answer the user.
    """
    results = await _search_archival(query, limit, track_usage=False)
    return {"results": results}


async def _search_archival(
    query: str,
    limit: int,
    *,
    track_usage: bool,
) -> list[dict[str, Any]]:
    session_maker = session_factory()
    async with session_maker() as session:
        matches = await semantic_search_archival(session, query, limit=limit)
        if track_usage and matches:
            await mark_archival_used(session, [result.id for result in matches])
    return [
        {
            "id": result.id,
            "content": result.content,
            "tags": result.tags,
            "confidence": result.confidence,
            "stability": result.stability,
            "salience": result.salience,
            "distance": result.distance,
        }
        for result in matches
    ]


@tool
async def insert_archival_fact(
    content: str,
    tags: list[str] | None = None,
    confidence: int = 2,
    stability: str = "long_term",
    salience: int = 2,
    source: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Insert a new archival fact about the user.

    POLICY:
      - Only call for cross-conversation user facts: preferences, habits,
        lessons, identity, goals, skills, hobbies, entertainment preferences,
        lifestyle habits, relaxation patterns, and stable likes/dislikes.
      - Do NOT call for temporary state, one-off events, today's plan, or
        short-term mood unless the user confirms it is a stable pattern.
      - Do NOT call for project-specific facts (those belong in CLAUDE.md).
      - This NEVER writes to core_blocks; those are owned by the Sleep agent.
      - Signal policy: confidence=factual certainty, stability=time horizon,
        salience=future usefulness. If one user message mixes stable and
        temporary information, split the memories instead of storing all as one
        high-salience long_term fact.

    Args:
        content: The fact about the user, in natural language.
        tags: Topical tags (e.g. ["preference", "code-style"]).
        confidence: 1=tentative, 2=partly confirmed, 3=explicitly stated.
        stability: "long_term", "stage", or "temporary".
        salience: 1=low, 2=medium, 3=high future usefulness.
        source: Where this fact came from (session id or origin tag).
        reason: Brief rationale for storing it.
    """
    session_maker = session_factory()
    async with session_maker() as session:
        fact_id = await insert_archival(
            session,
            content=content,
            tags=tags,
            confidence=confidence,
            stability=stability,
            salience=salience,
            source=source,
            actor=AWAKE_ACTOR,
            reason=reason,
        )
    return {"status": "ok", "fact_id": fact_id, "content": content}


@tool
async def get_overview() -> dict[str, Any]:
    """Quick overview: core block summaries + archival total.

    Use this at the start of a new conversation to know who the user is.
    """
    session_maker = session_factory()
    async with session_maker() as session:
        ov = await get_memory_overview(session)
    return {
        "core_blocks": [
            {
                "label": b.label,
                "value_preview": b.value[:120],
                "version": b.version,
            }
            for b in ov.core_blocks
        ],
        "archival_total": ov.archival_count,
    }


@tool
async def forget_archival(fact_id: int, reason: str) -> dict[str, Any]:
    """Soft-delete an archival fact that turned out to be wrong/outdated.

    Args:
        fact_id: ID of the archival fact (returned from search_archival).
        reason: Why we're forgetting it.
    """
    session_maker = session_factory()
    async with session_maker() as session:
        await soft_delete_archival(
            session, fact_id, reason=reason, actor=AWAKE_ACTOR
        )
    return {"status": "ok", "fact_id": fact_id}


# Tool list for LangGraph create_react_agent.
AWAKE_TOOLS = [
    load_core,
    find_archival_duplicates,
    search_archival,
    insert_archival_fact,
    get_overview,
    forget_archival,
]
