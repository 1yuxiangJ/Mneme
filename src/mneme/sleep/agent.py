"""Sleep Agent: LangGraph StateGraph orchestrating sleep-time consolidation.

Per Letta sleep-time compute (arxiv 2504.13171), this agent is the SOLE
writer of core_blocks. The Awake agent only writes archival; Sleep promotes
and consolidates.

A cycle proceeds through up to 8 nodes:
  1. snapshot    — clone main → *_staging
  2. plan        — LLM decides which subsequent phases to run
  3. consolidate — merge near-duplicates (staging only)
  4. promote     — lift archival → core_blocks (staging; only path to core)
  5. demote      — soft-delete stale low-confidence archival (staging)
  6. resolve     — fix internal contradictions in core_blocks (staging)
  7. reflect     — write "about user" snapshot to memory_ops_log
  8. swap        — atomic_swap staging → main

Budget enforcement:
  - max_wall_time (settings.sleep_max_wall_time_seconds, default 300s)
  - per-phase deadline check; skip phase if exceeded
  - max_tokens NOT enforced in MVP (Day 05+ improvement)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text as sql_text

from mneme.config import settings
from mneme.db.models import get_sessionmaker
from mneme.llm.client import get_chat_llm
from mneme.memory.store import MemoryOpDraft
from mneme.sleep import prompts, staging, tools

logger = logging.getLogger("mneme.sleep")

# In-process bookkeeping. For production, persist to DB.
_last_cycle_ts: datetime | None = None


class SleepState(TypedDict, total=False):
    snapshot_ts: datetime
    deadline_ts: float
    plan: list[str]
    consolidate_actions: list[Any]
    promote_actions: list[Any]
    demote_actions: list[Any]
    contradictions: list[Any]
    reflection_text: str
    pending_ops: list[MemoryOpDraft]
    aborted: bool
    abort_reason: str | None


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


async def _llm_json(prompt: str) -> dict[str, Any]:
    """Call chat LLM and parse JSON response (tolerant of code fences)."""
    llm = get_chat_llm(temperature=0.0)
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = _content_to_text(resp.content if hasattr(resp, "content") else resp)
    return _safe_parse_json(raw)


def _safe_parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
        return {"_raw": parsed}
    except json.JSONDecodeError as exc:
        logger.warning("LLM JSON parse failed; raw[:500]=%r", raw[:500])
        return {"_parse_error": str(exc), "_raw": raw[:1000]}


def _budget_ok(state: SleepState) -> bool:
    return state.get("deadline_ts", float("inf")) > time.monotonic()


def _append_pending_ops(
    state: SleepState,
    pending_ops: list[MemoryOpDraft],
) -> SleepState:
    if not pending_ops:
        return state
    return {
        **state,
        "pending_ops": [*state.get("pending_ops", []), *pending_ops],
    }


# ---------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------


async def node_snapshot(state: SleepState) -> SleepState:
    if not _budget_ok(state):
        return {**state, "aborted": True, "abort_reason": "deadline before snapshot"}
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        ts = await staging.snapshot_to_staging(session)
    logger.info("snapshot_to_staging @ %s", ts)
    return {**state, "snapshot_ts": ts}


async def node_plan(state: SleepState) -> SleepState:
    if state.get("aborted") or not _budget_ok(state):
        return state
    global _last_cycle_ts
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        summary = await tools.summarize_state(session, _last_cycle_ts)

    rendered = prompts.PLAN_PROMPT.format(
        state_summary=json.dumps({
            "core_blocks": summary.core_blocks,
            "archival_count": summary.archival_count,
            "new_since_last_cycle": summary.new_archival_since_last_cycle,
            "stale_count": summary.stale_archival_count,
            "has_high_freq": summary.has_high_freq_archival,
        }, indent=2, default=str),
        min_archival=settings.sleep_min_archival_count,
    )
    decision = await _llm_json(rendered)
    phases = decision.get("phases", ["reflect"])
    logger.info("plan: phases=%s reason=%s", phases, decision.get("reason"))
    return {**state, "plan": phases}


async def node_consolidate(state: SleepState) -> SleepState:
    if (
        state.get("aborted")
        or "consolidate" not in state.get("plan", [])
        or not _budget_ok(state)
    ):
        return state
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        clusters = await tools.find_consolidation_clusters(session)
        if not clusters:
            logger.info("consolidate: no clusters found")
            return {**state, "consolidate_actions": []}
        rendered = prompts.CONSOLIDATE_PROMPT.format(
            clusters_json=json.dumps(clusters, indent=2, default=str),
        )
        decision = await _llm_json(rendered)
        actions = decision.get("actions", [])
        pending_ops = await tools.apply_consolidation(session, actions)
    logger.info("consolidate: %d actions", len(actions))
    return _append_pending_ops(
        {**state, "consolidate_actions": actions},
        pending_ops,
    )


async def node_promote(state: SleepState) -> SleepState:
    if (
        state.get("aborted")
        or "promote" not in state.get("plan", [])
        or not _budget_ok(state)
    ):
        return state
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        candidates = await tools.get_promote_candidates(session)
        if not candidates:
            logger.info("promote: no candidates")
            return {**state, "promote_actions": []}
        summary = await tools.summarize_state(session, None)
        rendered = prompts.PROMOTE_PROMPT.format(
            core_blocks_json=json.dumps(summary.core_blocks, indent=2, default=str),
            candidates_json=json.dumps(candidates, indent=2, default=str),
        )
        decision = await _llm_json(rendered)
        actions = decision.get("actions", [])
        pending_ops = await tools.apply_promotions(session, actions)
    logger.info("promote: %d actions", len(actions))
    return _append_pending_ops(
        {**state, "promote_actions": actions},
        pending_ops,
    )


async def node_demote(state: SleepState) -> SleepState:
    if (
        state.get("aborted")
        or "demote" not in state.get("plan", [])
        or not _budget_ok(state)
    ):
        return state
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        stale = await tools.get_stale_candidates(session)
        if not stale:
            logger.info("demote: no candidates")
            return {**state, "demote_actions": []}
        rendered = prompts.DEMOTE_PROMPT.format(
            stale_json=json.dumps(stale, indent=2, default=str),
        )
        decision = await _llm_json(rendered)
        actions = decision.get("actions", [])
        pending_ops = await tools.apply_demotions(session, actions)
    logger.info("demote: %d actions", len(actions))
    return _append_pending_ops(
        {**state, "demote_actions": actions},
        pending_ops,
    )


async def node_resolve(state: SleepState) -> SleepState:
    if (
        state.get("aborted")
        or "resolve" not in state.get("plan", [])
        or not _budget_ok(state)
    ):
        return state
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        summary = await tools.summarize_state(session, None)
        recent = (await session.execute(sql_text(
            "SELECT op_type, actor, target_kind, target_id, reason, ts "
            "FROM memory_ops_log ORDER BY ts DESC LIMIT 20"
        ))).all()
        ops = [
            {
                "op_type": r.op_type, "actor": r.actor,
                "target_kind": r.target_kind, "target_id": r.target_id,
                "reason": r.reason,
                "ts": r.ts.isoformat() if r.ts else None,
            }
            for r in recent
        ]
        rendered = prompts.RESOLVE_PROMPT.format(
            core_blocks_json=json.dumps(summary.core_blocks, indent=2, default=str),
            recent_ops_json=json.dumps(ops, indent=2, default=str),
        )
        decision = await _llm_json(rendered)
        contradictions = decision.get("contradictions", [])
        pending_ops = await tools.apply_resolutions(session, contradictions)
    logger.info("resolve: %d contradictions", len(contradictions))
    return _append_pending_ops(
        {**state, "contradictions": contradictions},
        pending_ops,
    )


async def node_reflect(state: SleepState) -> SleepState:
    if (
        state.get("aborted")
        or "reflect" not in state.get("plan", [])
        or not _budget_ok(state)
    ):
        return state
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        summary = await tools.summarize_state(session, None)
        rows = (await session.execute(sql_text(
            "SELECT id, content, confidence, stability, salience, use_count "
            "FROM archival_facts_staging "
            "WHERE is_deleted = FALSE "
            "ORDER BY salience DESC, confidence DESC, use_count DESC LIMIT 5"
        ))).all()
        highlights = [
            {"id": r.id, "content": r.content,
             "confidence": r.confidence, "stability": r.stability,
             "salience": r.salience, "use_count": r.use_count}
            for r in rows
        ]
        rendered = prompts.REFLECT_PROMPT.format(
            core_blocks_json=json.dumps(summary.core_blocks, indent=2, default=str),
            archival_highlights_json=json.dumps(highlights, indent=2, default=str),
        )
        llm = get_chat_llm(temperature=0.3)
        resp = await llm.ainvoke([HumanMessage(content=rendered)])
        reflection_text = _content_to_text(
            resp.content if hasattr(resp, "content") else resp
        )
        pending_ops = [tools.draft_reflection_log(reflection_text)]
    logger.info("reflect: snapshot logged")
    return _append_pending_ops(
        {**state, "reflection_text": reflection_text},
        pending_ops,
    )


async def node_swap(state: SleepState) -> SleepState:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        if state.get("aborted"):
            logger.warning("swap aborted: %s; cleaning up staging",
                           state.get("abort_reason"))
            await staging.cleanup_staging(session)
            return state
        ts = state.get("snapshot_ts")
        if ts is None:
            logger.warning("no snapshot ts; cleaning up staging")
            await staging.cleanup_staging(session)
            return state
        await staging.atomic_swap(session, ts, pending_ops=state.get("pending_ops", []))
        logger.info("atomic_swap complete")
    return state


# ---------------------------------------------------------------
# Graph
# ---------------------------------------------------------------


def build_sleep_graph() -> Any:
    g = StateGraph(SleepState)
    g.add_node("snapshot", node_snapshot)
    g.add_node("plan", node_plan)
    g.add_node("consolidate", node_consolidate)
    g.add_node("promote", node_promote)
    g.add_node("demote", node_demote)
    g.add_node("resolve", node_resolve)
    g.add_node("reflect", node_reflect)
    g.add_node("swap", node_swap)

    g.add_edge(START, "snapshot")
    g.add_edge("snapshot", "plan")
    g.add_edge("plan", "consolidate")
    g.add_edge("consolidate", "promote")
    g.add_edge("promote", "demote")
    g.add_edge("demote", "resolve")
    g.add_edge("resolve", "reflect")
    g.add_edge("reflect", "swap")
    g.add_edge("swap", END)
    return g.compile()


_graph: Any = None


def get_sleep_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = build_sleep_graph()
    return _graph


# ---------------------------------------------------------------
# Public entrypoint (called by scheduler)
# ---------------------------------------------------------------


async def run_sleep_cycle() -> dict[str, Any]:
    """Run one full Sleep cycle.

    Returns a summary dict for logging / observability.
    """
    global _last_cycle_ts
    graph = get_sleep_graph()
    deadline = time.monotonic() + settings.sleep_max_wall_time_seconds
    init_state: SleepState = {
        "deadline_ts": deadline,
        "aborted": False,
        "abort_reason": None,
    }
    logger.info("sleep cycle starting (budget=%ds)",
                settings.sleep_max_wall_time_seconds)
    try:
        final_state = await graph.ainvoke(init_state)
    except Exception as exc:
        logger.exception("sleep cycle failed: %s", exc)
        try:
            session_maker = get_sessionmaker()
            async with session_maker() as session:
                await staging.cleanup_staging(session)
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}

    if not final_state.get("aborted"):
        _last_cycle_ts = datetime.now(UTC)

    return {
        "status": "aborted" if final_state.get("aborted") else "ok",
        "abort_reason": final_state.get("abort_reason"),
        "plan": final_state.get("plan", []),
        "consolidate_count": len(final_state.get("consolidate_actions") or []),
        "promote_count": len(final_state.get("promote_actions") or []),
        "demote_count": len(final_state.get("demote_actions") or []),
        "contradictions_count": len(final_state.get("contradictions") or []),
        "reflection_preview": (final_state.get("reflection_text") or "")[:200],
    }
