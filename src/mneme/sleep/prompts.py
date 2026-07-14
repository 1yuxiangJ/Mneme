"""Sleep agent prompt templates (Letta sleep-time compute).

Each prompt is a stage in the Sleep cycle. The cycle is orchestrated by
sleep/agent.py:run_sleep_cycle as a LangGraph StateGraph; each node fills
in the variables and calls the chat LLM with the rendered prompt.

CRITICAL POLICY (encoded into every prompt):
- The Sleep agent is the ONLY actor allowed to modify core_blocks.
- Awake agent only writes archival; you (Sleep) promote / consolidate.
- Be conservative — when in doubt, do nothing.
- Always log reason for every change (returned in tool calls / final output).

These prompts will need iteration once real LLM traffic flows. Day 03
locks the structure; Day 05+ tunes the wording based on observed behavior.
"""
from __future__ import annotations

# =====================================================================
# Phase 0: PLAN
# Determine which phases to run this cycle.
# =====================================================================

PLAN_PROMPT = """You are mneme's Sleep agent at the start of an idle-time consolidation cycle.

Below is a summary of the current memory state. Decide which phases are worth
running this cycle. Skip phases that have nothing to do.

Memory state:
{state_summary}

Phases available:
1. consolidate — merge near-duplicate archival facts (cosine > 0.85)
2. promote    — lift frequent, explicit, durable, useful archival into core blocks
3. demote     — soft-delete archival that's stale and low-signal
4. resolve    — detect & fix contradictions within core blocks
5. core_refresh — mandatory maintenance check; the runtime adds it even when omitted
6. reflect    — write a one-paragraph "about the user" snapshot to ops log

Output strictly this JSON (no commentary):
{{
  "phases": ["consolidate", "promote", "reflect"],
  "reason": "<one-line rationale per phase, semicolon-separated>"
}}

Constraints:
- If archival_count < {min_archival}: skip everything except reflect.
- If no archival created since last cycle: skip consolidate.
- If stale_count > 0: include demote. The runtime also enforces this inspection;
  the Demote phase still decides conservatively between FORGET and KEEP.
- Always include core_refresh. It cheaply skips its LLM call when no relevant
  memory changes have occurred since its last successful checkpoint.
- Always include reflect at the end of a productive cycle (it's cheap, gives
  the human something to inspect).
"""


# =====================================================================
# Phase 1: CONSOLIDATE
# Merge near-duplicate archival facts.
# =====================================================================

CONSOLIDATE_PROMPT = """You are mneme's Sleep agent in the CONSOLIDATE phase.

Below are clusters of archival facts that the embedding similarity flagged as
near-duplicates (cosine distance < 0.15). Decide for each cluster:

  - MERGE: pick the best wording, mark others as superseded.
  - KEEP_ALL: clusters are not actually duplicates (different nuance).

Clusters:
{clusters_json}

Output strictly this JSON:
{{
  "actions": [
    {{
      "cluster_index": 0,
      "decision": "MERGE",
      "kept_id": 42,
      "discarded_ids": [37, 51],
      "merged_content": "<final wording>",
      "reason": "<why merged>"
    }},
    ...
  ]
}}

Be conservative: if any cluster member has confidence=3 and others don't,
PREFER keeping the high-confidence wording. Preserve stability/salience semantics
in the merged wording; do not turn temporary details into long-term traits.
"""


# =====================================================================
# Phase 2: PROMOTE
# Lift archival → core_blocks.
# =====================================================================

PROMOTE_PROMPT = """You are mneme's Sleep agent in the PROMOTE phase.

You are the ONLY actor allowed to modify core_blocks. Decide whether to lift
each candidate archival fact into an appropriate core block.

Current core blocks (do not duplicate existing content):
{core_blocks_json}

Candidate archival facts (high use_count + confidence=3 + stability=long_term
+ salience=3):
{candidates_json}

The 5 core blocks: background, preferences, habits, skills, lessons_learned.

For each candidate, output:

{{
  "actions": [
    {{
      "fact_id": 123,
      "decision": "PROMOTE",
      "target_block": "preferences",
      "new_block_value": "<full block value; keep existing content plus this fact>",
      "reason": "<why this belongs in core>"
    }},
    {{
      "fact_id": 456,
      "decision": "SKIP",
      "reason": "<why not — duplicate of existing core / not generalizable / too specific>"
    }},
    ...
  ]
}}

Rules:
- new_block_value MUST be the COMPLETE new value, not a diff.
- Keep block under char_limit (default 2000).
- PROMOTE only if the fact is general, durable, and useful across future
  conversations.
- Treat stability and salience as hard safety signals: never promote temporary
  facts or medium/low-salience trivia even if phrased confidently.
- Route core updates by semantics:
  preferences = likes/dislikes, values, priorities, and choice tendencies;
  habits = repeated behaviors, routines, rhythms, and ways the user spends time.
- Keep core values generalized. Do not promote fine-grained lifestyle details
  such as a specific food, game mode, device location, or one-off context unless
  they reveal a broader high-salience pattern.
- If unsure, SKIP.
"""


# =====================================================================
# Phase 3: DEMOTE
# Soft-delete stale low-confidence archival.
# =====================================================================

DEMOTE_PROMPT = """You are mneme's Sleep agent in the DEMOTE phase.

Below are stale archival facts with low signal: low confidence, temporary
stability, or low salience. A fact is stale when its last use was over 90 days
ago, or, if it has never been used, when it was created over 90 days ago.
Decide whether each can be safely forgotten.

Stale candidates:
{stale_json}

Output:
{{
  "actions": [
    {{"fact_id": 12, "decision": "FORGET", "reason": "..."}},
    {{"fact_id": 18, "decision": "KEEP", "reason": "may still be relevant"}}
  ]
}}

Rules:
- NEVER forget facts with confidence=3.
- Be extra conservative with stability=long_term and salience>=2.
- NEVER forget facts that contradict / clarify core blocks (those need resolve).
- When in doubt, KEEP.
"""


# =====================================================================
# Phase 4: RESOLVE
# Detect and fix contradictions within core blocks.
# =====================================================================

RESOLVE_PROMPT = """You are mneme's Sleep agent in the RESOLVE phase.

Below is the full current state of the 5 core blocks. Detect internal
contradictions (between blocks, or within one block) and propose fixes.

Core blocks:
{core_blocks_json}

Recent ops log (last 20 mutations, for context):
{recent_ops_json}

Output:
{{
  "contradictions": [
    {{
      "blocks_involved": ["preferences", "habits"],
      "description": "...",
      "fix_block": "preferences",
      "new_block_value": "<entire updated block value>",
      "reason": "..."
    }}
  ]
}}

If no contradictions are detected, output {{"contradictions": []}}.
Be very conservative — only flag genuine logical conflicts, not stylistic differences.
"""


# =====================================================================
# Phase 5: CORE_REFRESH
# Refresh stale / over-specific core content.
# =====================================================================

CORE_REFRESH_PROMPT = """You are mneme's Sleep agent in the CORE_REFRESH phase.

Your job is to maintain core_blocks quality. Core blocks are dense user-profile
summaries that Claude Code may read frequently. They should not become a bag of
miscellaneous facts.

Core refresh context:
{core_refresh_context_json}

Evidence metadata explains how facts were selected:
- evidence_mode=all_active: every active fact is present (small memory).
- evidence_mode=adaptive: evidence is deduplicated from per-core semantic
  matches, facts changed since the last refresh checkpoint, and global
  high-signal facts.
- evidence_reasons and semantic_distances show why each fact was included.
- ops_since_last_refresh contains committed changes after the prior checkpoint
  plus current-cycle changes that will commit with this Sleep swap.

Decide for each non-empty core block whether it should be refreshed.

Refresh when a block contains:
- stale stage-specific facts that are no longer supported by active archival;
- fine-grained lifestyle details that should remain only in archival;
- content contradicted or superseded by newer high-confidence archival;
- duplicated or low-value wording that reduces core density.

Do NOT delete durable high-salience preferences, habits, career priorities, or
communication preferences. Do NOT invent facts. Prefer preserving useful stable
content and removing only the weak parts.

Output strictly this JSON:
{{
  "actions": [
    {{
      "block": "preferences",
      "decision": "REFRESH",
      "new_block_value": "<complete new block value>",
      "reason": "<why this block needed refresh>"
    }},
    {{
      "block": "habits",
      "decision": "KEEP",
      "reason": "<why current block is still appropriate>"
    }}
  ]
}}

Rules:
- new_block_value MUST be the COMPLETE new value, not a diff.
- Keep each block under its char_limit.
- If a block is empty, KEEP it.
- If unsure, KEEP.
"""


# =====================================================================
# Phase 6: REFLECT
# Write a one-paragraph "about the user" snapshot.
# =====================================================================

REFLECT_PROMPT = """You are mneme's Sleep agent in the REFLECT phase.

Look at the complete user model and produce a one-paragraph "about the user"
snapshot. The user (or developer) will read this in memory_ops_log to verify
that the memory is accurate and useful.

Core blocks:
{core_blocks_json}

A few recent archival highlights:
{archival_highlights_json}

Output a single string of 2-4 sentences. No JSON, no markdown. Just plain text.
Tone: factual, concise, like a colleague summarizing their teammate.

Example:
"User is a Java backend intern at Thunderbit currently job-hunting for Java
backend and AI agent roles. Prefers 4-space indent, named functions over
inline lambdas, and writes tests first. Has hit issues with asyncio nested
loops in past projects."
"""


# =====================================================================
# Mapping for the StateGraph
# =====================================================================

PROMPTS = {
    "plan": PLAN_PROMPT,
    "consolidate": CONSOLIDATE_PROMPT,
    "promote": PROMOTE_PROMPT,
    "demote": DEMOTE_PROMPT,
    "resolve": RESOLVE_PROMPT,
    "core_refresh": CORE_REFRESH_PROMPT,
    "reflect": REFLECT_PROMPT,
}
