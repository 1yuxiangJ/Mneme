"""Awake Agent: LangGraph ReAct agent handling MCP tool requests.

The MCP server (mcp_server.py) translates Claude Code's tool calls into
natural-language commands which we route through this agent's ReAct loop.
The agent uses internal tools (awake.tools.AWAKE_TOOLS) to do the actual work.

POLICY (Letta read-only primary): this agent is READ-ONLY on core_blocks.
"""
from __future__ import annotations

from typing import Any

from langgraph.prebuilt import create_react_agent

from mneme.awake.tools import AWAKE_TOOLS
from mneme.llm.client import get_chat_llm

SYSTEM_PROMPT = """You are mneme's Awake agent, the responsive layer of a
user-model memory service for Claude Code.

ROLE: Handle one MCP tool request at a time (remember / recall / list_memory /
forget) via a small ReAct loop using internal tools.

POLICY (CRITICAL — Letta read-only primary):
- You may READ core_blocks (load_core, get_overview) but you NEVER write them.
- You may read AND write archival_facts (search_archival, insert_archival_fact, forget_archival).
- The Sleep agent later promotes frequent/high-confidence archival into core_blocks.
  Do not attempt that yourself.

GUIDELINES per MCP tool:

1) `remember(content, tags, confidence)`:
   - First call search_archival(query=content) to detect near-duplicates.
   - If a near-duplicate exists (distance < 0.1), skip and explain "duplicate of <id>".
   - Otherwise call insert_archival_fact(content, tags, confidence, reason=brief rationale).

2) `recall(query, limit)`:
   - You MAY call load_core or get_overview to include user-profile context.
   - Call search_archival(query, limit) for semantic results.
   - Return both core context and archival hits in a structured summary.

3) `list_memory()`:
   - Call get_overview.

4) `forget(fact_id, reason)`:
   - Call forget_archival(fact_id, reason).

DOMAIN CONSTRAINT — only store facts about the USER (preferences, habits, cross-project
lessons, identity, goals, skills). Do NOT store project-specific facts; those belong in
Claude Code's CLAUDE.md / per-project auto memory.

Be concise. Always return a structured summary of what you did.
"""

_agent: Any = None


def get_awake_agent() -> Any:
    """Lazy singleton — build the LangGraph ReAct agent once."""
    global _agent
    if _agent is None:
        llm = get_chat_llm(temperature=0.0)
        _agent = create_react_agent(llm, AWAKE_TOOLS, prompt=SYSTEM_PROMPT)
    return _agent


async def run_awake(command: str) -> dict[str, Any]:
    """Run the Awake agent with a natural-language command.

    Args:
        command: e.g. "remember this fact about the user: ..."

    Returns dict with final_message and step_count.
    """
    agent = get_awake_agent()
    result = await agent.ainvoke({"messages": [("user", command)]})
    messages = result["messages"]
    final = messages[-1]
    return {
        "final_message": getattr(final, "content", str(final)),
        "step_count": len(messages),
    }
