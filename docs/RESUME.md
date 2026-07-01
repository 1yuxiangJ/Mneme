# mneme — 简历项目描述

> 中英 × 短中长 = 6 个版本。按场景拷贝。

---

## 中文 · 短版(1 行 — 简历项目栏)

> mneme:基于 Letta sleep-time compute paper 实现的 Claude Code 跨项目长期记忆服务。Python + MCP + LangGraph + PostgreSQL/pgvector,Awake/Sleep 双 agent + read-only primary 架构。

---

## 中文 · 中版(3-4 句 — GitHub 简介 / 求职 deck 一页)

> mneme 是给 Claude Code 装的跨 project 用户画像长期记忆服务。通过 MCP 协议接入,Awake agent 用 LangGraph ReAct 响应 remember/recall 请求,Sleep agent 用 LangGraph StateGraph 在 idle 时做 consolidation / promotion / reflection。严格按 Letta sleep-time compute paper(arxiv 2504.13171)实现 read-only primary 模式——Awake 只读 core,Sleep 是 core_blocks 的 sole writer。设计了 staging snapshot + atomic swap 解决双 agent 并发改 memory 的一致性问题。Stack:Python 3.11 + FastAPI + LangGraph + langchain-openai + PostgreSQL + pgvector + APScheduler。

---

## 中文 · 长版(1 段 — Cover Letter / 项目主页 about)

> mneme 是参考 Letta sleep-time compute paper 自研的 stateful user-model memory service,作为 Claude Code 的外置长期记忆基础设施,补 Claude Code 自带 CLAUDE.md 和 per-project auto memory 不覆盖的 cross-project 空白。通过 MCP(Model Context Protocol)接入,提供 `remember` / `recall` / `list_memory` / `forget` 四个 tool。
>
> 架构上**严格分离 Awake / Sleep 双 agent 的读写权限**:Awake agent 用 LangGraph `create_react_agent` 处理实时请求,只读 core_blocks 和读/写 archival_facts;Sleep agent 用 LangGraph `StateGraph` 实现 8 阶段 cycle(snapshot → plan → consolidate → promote → demote → resolve → reflect → swap),是 core_blocks 的唯一 writer。Read-only primary 通过三道保险落地:Awake system prompt 教 LLM 别尝试改 core、应用层 `memory.store` 抛 `PermissionError` 并写 `policy_violation` 到 ops log、`core_blocks.last_writer` DB 字段自检。
>
> Sleep cycle 用 **staging snapshot + atomic swap** 保证并发安全:启动时 `CREATE TABLE LIKE` clone 主表为 staging,Sleep 期间只动 staging,完成时单 transaction 内合并 Awake 期间的新 archival(`created_at > snapshot_ts`),三步 `RENAME` 切换。APScheduler 双触发:idle ≥ 30 min 自动 fire,daily cron 03:00 兜底,模块级 `_cycle_running` flag 防并发。
>
> 完整 2103 行 Python(17 模块)+ 6 个 reflection prompt 模板 + 幂等 SQL schema + pytest 测试 + 幂等 setup.sh。Stack:Python 3.11 / FastAPI / mcp / LangGraph / langchain-openai / SQLAlchemy async / asyncpg / pgvector / APScheduler / pytest。LLM 全程 DeepSeek-chat(成本)+ embedding 阿里通义 text-embedding-v3(1024 维,dashscope OpenAI-compatible)。

---

## 英文 · 短版(1 line — Resume entry)

> **mneme**: Cross-project user-model memory service for Claude Code via MCP, implementing Letta's sleep-time compute (arxiv 2504.13171) with Awake/Sleep dual-agent architecture and strict read-only primary semantics. Python + LangGraph + PostgreSQL/pgvector.

---

## 英文 · 中版(3-4 sentences — GitHub bio / one-page deck)

> **mneme** is a stateful user-model memory service for Claude Code, exposed over the Model Context Protocol. An Awake agent (LangGraph ReAct) handles real-time `remember`/`recall`/`list_memory`/`forget` requests; a Sleep agent (LangGraph StateGraph, 8 phases) runs autonomous consolidation, promotion, demotion, conflict resolution, and reflection during idle periods.
>
> Strict adherence to Letta's sleep-time compute paper (arxiv 2504.13171): the Awake agent is **read-only on `core_blocks`**; the Sleep agent is the **sole writer of `core_blocks`**. Enforced at three layers (prompt + application-layer guard + DB self-check column). Concurrency via staging snapshot + atomic table swap. Stack: Python 3.11, FastAPI, LangGraph, langchain-openai, PostgreSQL + pgvector, APScheduler.

---

## 英文 · 长版(1 paragraph — Cover Letter / project landing)

> **mneme** is a stateful user-model memory service for Claude Code, designed as cross-project memory infrastructure to complement Claude Code's per-project CLAUDE.md and auto-memory. Communication is via the Model Context Protocol (MCP) over streamable HTTP.
>
> The architecture strictly follows Letta's sleep-time compute paper (arxiv 2504.13171): an Awake agent and a Sleep agent share one memory store with read/write permission separation. The Awake agent — implemented with LangGraph's `create_react_agent` — handles real-time MCP tool requests via a small ReAct loop using internal tools for searching, inserting, and overviewing memory. It can **read** `core_blocks` (the user's structured profile) but **never write** them; writes are confined to `archival_facts`.
>
> The Sleep agent is the sole writer of `core_blocks`. Implemented as a LangGraph `StateGraph` with eight nodes (snapshot → plan → consolidate → promote → demote → resolve → reflect → swap), it triggers on either Awake-idle (≥30 min) or daily cron (03:00). Each phase uses a tailored reflection prompt; the plan phase is LLM-driven and decides which subsequent phases actually run, giving the cycle autonomous control over its own scope.
>
> Read-only primary is enforced at three layers: (1) the Awake agent's system prompt explicitly forbids core writes; (2) the `memory.store` application layer raises `PermissionError` and logs `policy_violation` to `memory_ops_log` if a non-sleep actor attempts a core write; (3) the `core_blocks.last_writer` column provides a DB-level self-check.
>
> Concurrency is handled via staging snapshot + atomic swap: the Sleep cycle clones the main tables into `*_staging` at startup, mutates only staging throughout, then atomically swaps via a single-transaction three-way `RENAME` (merging new archival rows inserted by Awake during the cycle via `created_at > snapshot_ts`). APScheduler enforces single-flight across triggers.
>
> Codebase: ~2,100 lines of Python across 17 modules, plus 6 reflection prompt templates, an idempotent SQL schema with HNSW vector index, pytest with integration-test gating, and a one-shot `setup.sh`. LLM: DeepSeek-chat for both agents (cost); embedding: 阿里通义 `text-embedding-v3` (1024 dim, OpenAI-compatible via dashscope).

---

## 项目仓库描述(GitHub repo description,160 字符)

- 中:`给 Claude Code 装的跨项目长期记忆服务,严格按 Letta sleep-time paper 设计 (arxiv 2504.13171),Awake/Sleep 双 agent + read-only primary。Python/MCP/LangGraph/PG/pgvector。`

- 英:`Letta-inspired user-model memory service for Claude Code via MCP. Awake/Sleep dual-agent, strict read-only primary, sleep-time consolidation. Python/LangGraph/PG/pgvector.`

---

## 关键词(SEO / LinkedIn skills)

stateful agent, MCP, Model Context Protocol, Claude Code, Letta, sleep-time compute, LangGraph, ReAct, autonomous reflection, FastAPI, PostgreSQL, pgvector, vector search, HNSW, memory consolidation, agent infrastructure

---

## 简历 bullet 形式(用于 backend 岗位简历)

```
mneme — Memory-as-a-Service for Claude Code · 个人项目(自研开源) · 2026-06

* 基于 Letta sleep-time compute paper (arxiv 2504.13171) 实现 Awake/Sleep
  双 agent 架构的跨项目长期记忆服务,通过 MCP 协议接入 Claude Code
* Read-only primary 模式三层保险:prompt 约束 + 应用层 PermissionError
  + DB last_writer 字段自检,避免 race
* Sleep cycle 用 staging snapshot + atomic swap (三步 RENAME in single tx)
  解决双 agent 并发改 memory 的一致性问题,Awake 不阻塞
* LangGraph StateGraph 实现 Sleep 的 8 阶段 cycle (snapshot/plan/
  consolidate/promote/demote/resolve/reflect/swap),plan 阶段 LLM 自主
  决定后续 phase
* Python 3.11 + FastAPI + LangGraph + PostgreSQL + pgvector (HNSW)
  + APScheduler,2100 行,17 模块
```

---

## 简历 bullet 形式(用于 AI / agent 岗位简历)

```
mneme — Letta-inspired stateful agent runtime · 个人项目(自研) · 2026-06

* 自研 Letta sleep-time compute paper 实现版,Awake/Sleep 双 agent 架构,
  arxiv 2504.13171 报告该范式在 stateful 推理任务上 +13~18% 准确率
* MCP-compatible memory service:通过 Model Context Protocol 接入 Claude
  Code (host),理论可扩展到 Cursor/Cline/自建 agent
* LLM-driven memory writes(非 CRUD):LLM 在 prompt 引导下自主调
  remember/recall tool,Sleep agent 在 idle 时 autonomous 跑 reflection
* Plan-driven sleep cycle:Sleep agent 看 memory state 自主决定本次跑哪些
  phase (consolidate/promote/demote/resolve/reflect),不是固定 cron
* Stack: LangGraph (Awake ReAct + Sleep StateGraph) / FastAPI / mcp SDK
  / SQLAlchemy async / pgvector HNSW / APScheduler
```

---

## 一句话面试自我介绍

> "做了一个 mneme,给 Claude Code 装的跨项目长期记忆服务,严格按 Letta sleep-time paper 设计——Awake 响应,Sleep 后台做'梦' (consolidation / promotion / reflection)。代码 ~2100 行,Python + LangGraph + MCP + PG + pgvector。可以现场 demo 也可以白板讲架构。"
