# mneme — 总方案 (2026-06-17)

> **简短版本**:做 Letta-inspired memory-as-a-service,通过 MCP 接 Claude Code,提供**跨 project 的用户画像长期记忆**。Awake + Sleep 双 agent,后者实现 sleep-time consolidation(论文出处:Letta 团队)。Python + FastAPI + LangGraph + PG + pgvector + DeepSeek。MVP 5-7 天。

---

## 1. 项目定位

### 1.1 一句话

通过 MCP 协议给 Claude Code 加一层**跨 project 的用户画像长期记忆**,补 Claude Code 自带 memory(CLAUDE.md / auto memory)不覆盖的 cross-project 空白。

### 1.2 不是什么

- ❌ 不是 chatbot
- ❌ 不是 RAG 平台
- ❌ 不是 mem0 / cognee 的 fork
- ❌ 不是替代 Claude Code 自带 memory(故意收窄边界)
- ❌ 不是 multi-tenant SaaS(MVP 单用户)

### 1.3 是什么

- ✅ Letta-inspired stateful memory service
- ✅ 实现 Letta paper 的 sleep-time compute 机制
- ✅ Awake / Sleep 双 agent 架构(响应式 + 自主)
- ✅ **严格 read/write 权限分离**(照搬 Letta paper):**Awake 只读 core / 只写 archival,Sleep 是 core_blocks 的 sole writer**
- ✅ 通过 MCP 协议跟 Claude Code(及未来其他 MCP host)集成

### 1.4 简历定位

> Independent **user model memory service** for Claude Code, communicating via MCP protocol. Awake agent handles responsive remember/recall through ReAct loop; Sleep agent runs autonomous sleep-time consolidation (Letta paper) during idle periods—consolidating, promoting, and pruning memory blocks. Stack: Python + FastAPI + LangGraph + PostgreSQL + pgvector + DeepSeek.

---

## 2. 边界设计(关键!)

**只做跨 project 共享的 user model,不碰 project-scoped 内容**。这条边界是项目存在意义的根。

### 2.1 Claude Code 已有的 memory 层

| 层 | 范围 | 谁写 |
|---|---|---|
| Session context | 当前对话 | LLM in-context |
| CLAUDE.md | 当前 project | 用户手写 / Claude 协助 |
| auto memory | 当前 project(`~/.claude/projects/.../memory/`) | Claude Code LLM 自己写 |

→ **Project 内的事实 Claude Code 三层全包**。我们不抢。

### 2.2 mneme 的唯一职责

**跨 project 的"关于用户这个人"的 fact**:
- 偏好(代码风格 / 工具选型)
- 习惯(工作流 / 测试习惯)
- 跨项目教训
- 用户画像(身份 / 背景 / 技能)

→ 这是 Claude Code per-project auto memory **故意不覆盖**的部分。

### 2.3 LLM 怎么判断"该不该写 mneme"

System prompt 约定:

> Only call `remember` for facts about the **user themselves** (preferences, habits, cross-project lessons, personal context). For project-specific facts, do not call this tool—those belong in CLAUDE.md or Claude Code's own auto memory.

LLM 看到 "我喜欢 4 空格" → 调 `remember`
LLM 看到 "thunderbit-server 用 Spring Boot 3" → **不调**(让 Claude Code auto memory 处理)

---

## 3. Letta 真实架构(借鉴源)

### 3.1 核心机制(基于源码 fetch 验证)

- **ReAct loop**:`step()` 方法 `while True` 循环
- **Heartbeat 机制**(Letta 独创):
  - tool 可设 `request_heartbeat=true` 强制 LLM 再走一轮
  - tool 失败自动 heartbeat 触发恢复
  - children_tools 自动 chain
- **LLM-driven memory writes**:LLM 通过 tool call 主动操作 memory(非 backend CRUD)
- **Tool Rules**:`terminal_tools` / `initial_tools` / `children_tools` 动态过滤 action space
- **Background summarization**:`summarize_messages_inplace()` 当 context 满了自动总结

### 3.2 Sleep-time compute(论文核心)

Letta 团队 2024 年提出。Agent 在 idle 时不浪费 compute,拿来处理 memory:

| 工作类型 | 干啥 |
|---|---|
| Consolidation | 把零散 archival 记忆合并、提炼 |
| Summarization | 老对话压缩成精简 summary |
| Promotion | 高频用的 archival 提升到 core block |
| Demotion / forgetting | stale 信息归档或删除 |
| Conflict resolution | 发现 memory 矛盾,主动解决 |

→ 跟人脑 REM 睡眠 memory consolidation 同构(神经科学的 memory replay)。

### 3.3 mneme 借鉴范围

- ✅ ReAct loop 思路(实现用 LangGraph,不手写)
- ✅ Memory blocks(core)+ archival 两层抽象
- ✅ LLM-driven memory writes(不是 CRUD)
- ✅ Sleep-time compute 完整机制(MVP 灵魂)
- ✅ **严格 read-only primary**:Awake 只读 core(只写 archival),Sleep 是 core_blocks 的 sole writer(基于 sleep-time blog 显式 fetch 确认)
- ❌ Heartbeat(MVP 不做,LangGraph 自带 loop)
- ❌ Tool Rules 动态约束(MVP 不做,system prompt 约束)
- ❌ 完整 multi-agent shared block 抽象(MVP 单 agent)

---

## 4. 架构

```
┌─────────────────────────────────────────┐
│  Claude Code (MCP host)                 │
│  - 当前 session context                  │
│  - CLAUDE.md / auto memory(project)    │
└──────────────────┬──────────────────────┘
                   │ MCP over HTTP
                   │ (localhost:8000/mcp)
                   ▼
┌─────────────────────────────────────────┐
│  mneme Memory Service                   │
│                                          │
│  ┌─────────────────┐                    │
│  │ MCP Server      │ ← FastAPI + mcp SDK│
│  │ - remember      │                    │
│  │ - recall        │                    │
│  │ - list_memory   │                    │
│  │ - forget        │                    │
│  └────────┬────────┘                    │
│           │                              │
│  ┌────────▼────────┐  ┌───────────────┐ │
│  │ Awake Agent     │  │ Sleep Agent   │ │
│  │ (LangGraph)     │  │ (LangGraph)   │ │
│  │ - responsive    │  │ - autonomous  │ │
│  │ - ReAct         │  │ - reflection  │ │
│  └────────┬────────┘  └──────┬────────┘ │
│           │                   │          │
│           └──────────┬────────┘          │
│                      ▼                   │
│         ┌────────────────────┐           │
│         │  Memory Store      │           │
│         │  - core_blocks     │           │
│         │  - archival_facts  │           │
│         │  - pgvector        │           │
│         │  + staging swap    │           │
│         └────────────────────┘           │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │ Sleep Trigger                     │   │
│  │ - APScheduler                     │   │
│  │ - idle ≥ 30min → fire             │   │
│  │ - cron 03:00 daily 兜底           │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 5. 数据模型(MVP 简化,两层)

### 5.1 Core blocks(结构化大颗粒)

5-7 个固定 label。**只有 Sleep agent 写入(Awake 只读)**——严格按 Letta sleep-time paper 的 read-only primary 模式。Awake 即使看到"用户表达了偏好"也只能 insert 到 archival,Sleep 后续 promote 决定是否升级到 core。

每个 label 内容示例:

| Label | 内容举例 |
|---|---|
| `background` | "Java backend 实习生 @ Thunderbit, 大三, 求职目标 校招 Java backend / AI agent 方向" |
| `preferences` | "4 空格, 偏 named function, 不喜欢 inline lambda 嵌套, Markdown 写文档" |
| `habits` | "先写测试再写实现, 大改动先 plan 文档, commit message 中文 OK" |
| `skills` | "Java/Spring Boot 强, Python 中, AI agent 学习中, 数据库基础扎实" |
| `lessons_learned` | "asyncio.gather 不要嵌 for loop, Spring Reactor 调试用 BlockHound, Strapi i18n translateAll 字段语义易误解" |

### 5.2 Archival facts(零散 fact + vector)

```sql
CREATE TABLE archival_facts (
    id            BIGSERIAL PRIMARY KEY,
    content       TEXT NOT NULL,
    tags          TEXT[],
    confidence    SMALLINT,  -- 1=low 2=med 3=high
    source        TEXT,       -- 哪个 session / 时间
    embedding     vector(1024),
    created_at    TIMESTAMPTZ DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    use_count     INT DEFAULT 0
);
CREATE INDEX ON archival_facts USING hnsw (embedding vector_cosine_ops);
```

### 5.3 Core blocks 表

```sql
-- 只允许 sleep agent 写入(应用层强制,见 last_writer 自检字段)
CREATE TABLE core_blocks (
    label         TEXT PRIMARY KEY,
    value         TEXT NOT NULL,
    char_limit    INT DEFAULT 2000,
    version       INT NOT NULL DEFAULT 1,
    updated_at    TIMESTAMPTZ DEFAULT now(),
    last_writer   TEXT DEFAULT 'sleep_agent'   -- 自检字段;若 Awake 试图写 core 应在应用层拒绝并 log
);
```

### 5.4 操作日志表(为 Sleep agent diff 用)

```sql
CREATE TABLE memory_ops_log (
    id            BIGSERIAL PRIMARY KEY,
    op_type       TEXT,       -- remember/recall/forget/sleep_consolidate/...
    actor         TEXT,       -- awake / sleep
    target_kind   TEXT,       -- core / archival
    target_id     TEXT,
    before_value  TEXT,
    after_value   TEXT,
    reason        TEXT,       -- LLM 给的解释
    ts            TIMESTAMPTZ DEFAULT now()
);
```

---

## 6. MCP Tools(暴露给 Claude Code)

**只暴露 4 个**,避免 LLM 选择困难。

### 6.1 `remember(content: str, tags?: List[str], confidence?: int)`
LLM 主动写入 archival fact。Awake agent 内部 ReAct loop 决定:
- 是否跟现有 archival 重复 → merge / skip
- 否则 insert 新 archival
- **绝不直接动 core_blocks**(Letta paper read-only primary)。需要影响 core 的高频/重要 fact 由 Sleep 在 promote 阶段升级。
- 落库后返回 fact_id + 写入摘要

### 6.2 `recall(query: str, limit?: int = 5)`
LLM 语义检索 memory。Awake agent 内部:
- core blocks 全量加载(便宜,只有几 KB)
- archival 向量检索 top-K
- 合并 + reranking → 返回结构化结果

### 6.3 `list_memory()`
列出当前所有 core block label + 摘要 + archival 总数。新 session 开始时 LLM 强烈建议调一次,知道用户是谁。

### 6.4 `forget(fact_id: str, reason: str)`
LLM 发现 fact 错误时调用,标记删除(soft delete + 日志)。

---

## 7. Awake Agent 详细

### 7.1 触发
MCP 收到 tool call → 触发 Awake Agent 内部 LangGraph 流程。

### 7.2 LangGraph 状态机(remember 场景)

```
START
  ↓
[Search Existing Archival]
  ↓
[Decide Action]  ← LLM 决定 (merge into existing archival / new archival / skip)
                   *绝不写 core_blocks(read-only primary)*
  ↓
[Insert/Update Archival]
  ↓
[Log + Return]
END
```

注:LLM 即使认为"该 fact 应进 core",Awake 也只 insert 到 archival。Sleep agent 在 promote 阶段判断是否升级到 core。

### 7.3 内部 LLM
- 模型:**DeepSeek-chat**
- 用 LangChain `ChatOpenAI`(base_url 指 DeepSeek)
- Tool calling 用 LangGraph 标准 ReAct 模板

---

## 8. Sleep Agent 详细(项目灵魂)

### 8.1 触发策略

- **Idle detection**:30 分钟无 Awake 调用 → 触发
- **Cron 兜底**:每日 03:00 强制运行一次
- **首次保护**:archival 总数 < 10 时跳过(没数据白跑)
- **单次 budget**:max 5 分钟 wall time + max 50k token

### 8.2 Sleep 任务清单(一次 sleep 跑完这些)

| 任务 | 干啥 |
|---|---|
| **Consolidate** | 找 archival 里语义相似的 (cosine > 0.85) 合并 |
| **Promote** | `use_count > 5` 且高 confidence 的 archival → 写入对应 core block(**Sleep 是 core_blocks 的 sole writer**) |
| **Demote / Forget** | `last_used_at > 90 days` 且 confidence=low → 标记删除 |
| **Conflict resolve** | LLM 扫一遍 core blocks,找矛盾,解决 |
| **Reflect** | LLM 综合所有 core blocks,输出一段"about user"自然语言摘要,写到 ops log(给人 review) |

### 8.3 LangGraph 状态机(sleep)

```
START
  ↓
[Load Snapshot]                ← Staging snapshot 当前 memory
  ↓
[LLM Plan]                     ← LLM 看 snapshot,plan 这次要做啥
  ↓
[Consolidate] → [Promote] → [Demote] → [ConflictResolve] → [Reflect]
  (每步 LLM driven,可跳过)
  ↓
[Validate Diff]                ← 检查 staging 跟原 snapshot diff 合理
  ↓
[Atomic Swap]                  ← 切换到 staging(transaction)
  ↓
[Log + Notify]
END
```

### 8.4 Reflection prompt 设计(MVP 草稿)

```
You are mneme's Sleep Agent. The user is asleep / not active. Your job:

1. Review current memory (core blocks + archival sample)
2. Plan: which of these should you do this cycle?
   - Consolidate duplicate facts
   - Promote frequent archival to core
   - Demote stale facts
   - Resolve contradictions
3. Execute plan via tools (consolidate / promote / demote / forget)
4. Output a brief "about user" reflection paragraph

Constraints:
- Be conservative. When in doubt, don't change.
- Never delete high-confidence facts.
- Always log reason for every change.
- You are the **only agent allowed to modify core_blocks**. The Awake agent only writes archival_facts. When promoting archival → core, validate carefully (high confidence + sufficient use_count).
```

---

## 9. 并发安全:Staging Snapshot + Atomic Swap

### 9.1 问题
Sleep agent 跑 5 分钟,期间 Awake 可能进 remember/recall 请求,改/读同一份 memory。

### 9.2 MVP 方案
1. Sleep 启动时:`SELECT *` snapshot 进 `archival_facts_staging` 和 `core_blocks_staging`
2. Sleep 全程**只动 staging**(core_blocks + archival_facts 都改)
3. Awake **只读 core_blocks 主表 + 只读/写 archival_facts 主表**(读写权限分离自然降低 conflict)
4. Sleep 完成时:
   - `BEGIN TRANSACTION`
   - 把主表期间的新 archival(`created_at > snapshot_ts`)合并进 staging
   - `ALTER TABLE archival_facts RENAME TO archival_facts_old;`
   - `ALTER TABLE archival_facts_staging RENAME TO archival_facts;`
   - `ALTER TABLE archival_facts_old RENAME TO archival_facts_staging;`
   - `COMMIT`
5. Awake 下次查询拿到新版本

**Trade-off**:期间 Awake 写入可能被 sleep 覆盖。MVP 接受,后续可加 conflict log。

### 9.3 完整版(post-MVP)
行级锁 + Awake/Sleep 操作 timestamp 对比 + 冲突时 sleep 让步。

---

## 10. LLM 选型 + Embedding

| 用途 | 模型 | 备注 |
|---|---|---|
| Awake Agent | `deepseek-chat` | 用户有额度 |
| Sleep Agent | `deepseek-chat` | 同上,reflection 也用 |
| Embedding | 阿里通义 `text-embedding-v3`(1024 维) | dashscope OpenAI-compatible 端口,国内付款,有免费额度 |
| Demo 录制 | (可选)Claude Sonnet 4 | 录像时质感 |

接入方式:LangChain `ChatOpenAI` + `base_url="https://api.deepseek.com/v1"`(OpenAI 兼容)

---

## 11. 完整 Tech Stack

```toml
# pyproject.toml 关键依赖
python = ">=3.11"
fastapi = "*"
uvicorn = "*"
mcp = "*"                    # 官方 MCP Python SDK
langgraph = "*"
langchain = "*"
langchain-openai = "*"
sqlalchemy = "*"
asyncpg = "*"
pgvector = "*"               # Python client
apscheduler = "*"
pydantic = "*"
python-dotenv = "*"
# dev
pytest = "*"
pytest-asyncio = "*"
```

外部依赖(用户回家装):
- PostgreSQL 16+
- pgvector extension

---

## 12. 实施路径(MVP 5-7 天)

| Day | 任务 | 备注 |
|---|---|---|
| **Day 01** | ✅ 目录骨架 + 文档 + 决策固化(本次) | 公司电脑做 |
| **Day 02** | 环境装好 + hello world(FastAPI 跑通 + DeepSeek 调通 + DB 连通) | 回家做 |
| **Day 03** | MCP server 框架 + 4 tools stub + 接入 Claude Code 验证 | |
| **Day 04** | Awake Agent(LangGraph)+ memory tools 真实实现 + e2e 跑通 remember/recall | |
| **Day 05** | Sleep Agent 框架 + reflection prompt + staging swap | |
| **Day 06** | 调优 + bug 修 + 真实 dogfooding 数据积累 | |
| **Day 07** | 测试 + demo 录制 + 简历项目描述定稿 | |

---

## 13. 风险

### 13.1 Memory 污染
LLM 把临时假设当 fact 写进去。
**缓解**:`remember` 强制带 confidence 字段,Sleep agent 定期清理 low confidence。

### 13.2 Demo 时 memory 是空的
**缓解**:正式 demo 前 2-3 天就开始用,真实积累 50+ 条。

### 13.3 LangGraph 学习曲线
**缓解**:用官方 ReAct example 模板套,改 prompt 即可。

### 13.4 MCP 协议踩坑
**缓解**:fetch 官方 SDK examples 抄。Python SDK 是 Anthropic 自维护,最成熟。

### 13.5 假深度退化为 CRUD
**核心 risk**。如果 Awake / Sleep 内部不真跑 ReAct loop,项目就退化为"LLM 包装的 memory CRUD"。
**缓解**:
- Awake remember 内部至少 3-step ReAct(search → decide → act)
- Sleep 内部至少 5-step ReAct(load → plan → multiple actions → validate → swap)
- Log 每一步 LLM 输出,demo 时展示

---

## 14. 面试 4 连问准备

1. **agent 怎么决策下一步?**
   → ReAct loop(LangGraph),LLM 看当前 memory state + tools + history 选 action

2. **action space 多大?**
   → Awake 4 个 MCP tool + 内部 memory ops;Sleep 5 类操作(consolidate/promote/demote/resolve/reflect)

3. **失败怎么 fallback?**
   → LangGraph error handler 节点,记 log + 跳过本步骤,不阻塞整个 loop

4. **跑了 20 步没结果咋办?**
   → max_iterations budget(Awake 10 步,Sleep 30 步)+ time budget(Sleep 5 分钟)。超了强制终止 + 报告

---

## 15. 简历叙事(终稿待定)

> 独立的 user model memory service,通过 MCP 协议为 Claude Code 提供跨 project 的用户画像长期记忆。**严格按 Letta sleep-time compute paper(arxiv 2504.13171)实现 read-only primary 模式**——Awake agent 只读 core memory + 只写 archival,Sleep agent 是 core_blocks 的 sole writer,在 idle 时执行 consolidation / promotion / reflection。读写权限分离 + staging snapshot + atomic swap 双重保证并发安全。FastAPI + LangGraph + PostgreSQL + pgvector + DeepSeek。

---

## 16. 演进 roadmap(MVP 后,简历可以放愿景章节)

1. Multi-user(MVP 单用户写死)
2. 接其他 MCP host(Cursor / Cline)
3. Memory 加密(敏感 fact 不进 LLM context)
4. Memory 可视化 UI(看 sleep agent 做的 diff)
5. Conflict 自动检测 + 用户确认流程
6. Memory 跨设备同步

---

## 17. Changelog

- **2026-06-17 Day 01**:首版方案落地(基于 Codex 提案 + Letta 源码 fetch + 与用户结构化讨论 Q1-Q13)
- **2026-06-17 Day 02(fetch refs 后调整)**:**照搬 Letta sleep-time compute paper 的 read-only primary 模式**
  - §1.3 / §3.3:加 "严格 read/write 权限分离" / "read-only primary" 借鉴项
  - §5.1 / §5.3:Core blocks 标注"只允许 Sleep 写入";SQL 加 `last_writer` 自检字段
  - §6.1 / §7.2:`remember` 严格只写 archival,Awake 状态机去掉 "new core" 分支
  - §8.2 / §8.4:Sleep promote 标 "sole writer of core",reflection prompt constraints 加权限说明
  - §9.2:并发说明加 read/write 权限分离描述
  - §15:简历叙事强化"严格 read-only primary 模式 + 读写权限分离"
