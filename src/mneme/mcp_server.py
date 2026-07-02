"""MCP server: 4 tools exposed to Claude Code via streamable-http transport.

Each tool here is a thin wrapper that:
  1. Builds a natural-language command describing the request.
  2. Delegates to the Awake agent's ReAct loop (awake.agent.run_awake).
  3. Returns the agent's structured summary.

The Awake agent then calls internal tools (search/insert/forget/etc.) per
its system prompt policy.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mneme.awake.agent import run_awake as _run_awake
from mneme.config import settings
from mneme.sleep.scheduler import mark_awake_activity


async def run_awake(command: str) -> dict[str, Any]:
    """Wrap Awake invocation to mark activity for the Sleep idle scheduler.

    Every MCP tool entry goes through this so idle detection works correctly.
    """
    mark_awake_activity()
    return await _run_awake(command)

mcp = FastMCP(
    "mneme",
    host=settings.mcp_server_host,
    port=settings.mcp_server_port,
)


@mcp.tool()
async def remember(
    content: str,
    tags: list[str] | None = None,
    confidence: int = 2,
) -> dict[str, Any]:
    """Store a fact about the user.

    ONLY call for cross-project user-level facts (preferences, habits, lessons,
    identity). For project-specific facts (architecture, library choices, project
    conventions), use CLAUDE.md or Claude Code's per-project auto memory instead.

    Args:
        content: The fact about the user.
        tags: Topical tags, e.g. ["preference", "code-style"].
        confidence: 1=low, 2=medium, 3=high.
    """
    tag_str = ", ".join(tags) if tags else "(none)"
    cmd = (
        "remember this fact about the user:\n"
        f"  content: {content}\n"
        f"  tags: {tag_str}\n"
        f"  confidence: {confidence}\n"
        "First check for near-duplicates via search_archival, then insert."
    )
    return await run_awake(cmd)


@mcp.tool()
async def recall(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantic search over the user's memory.

    Returns matching archival facts + core block context.

    Args:
        query: Natural-language query (e.g. "what are my code-style preferences?").
        limit: Max archival results (default 5).
    """
    cmd = (
        "recall: search the user's memory for facts relevant to:\n"
        f"  query: {query}\n"
        f"  limit: {limit}\n"
        "Include relevant core block context."
    )
    return await run_awake(cmd)


@mcp.tool()
async def list_memory() -> dict[str, Any]:
    """Overview of who the user is (all core blocks + archival total).

    Recommended at the start of a new conversation.
    """
    return await run_awake(
        "list_memory: give an overview of the stored user model "
        "(core blocks + archival total)."
    )


@mcp.tool()
async def forget(fact_id: int, reason: str) -> dict[str, Any]:
    """Soft-delete a fact discovered to be wrong/outdated.

    Args:
        fact_id: ID from a prior `recall` result.
        reason: Why we're forgetting it.
    """
    cmd = f"forget archival fact id={fact_id}; reason={reason}"
    return await run_awake(cmd)
