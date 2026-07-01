# Interview Q&A — 项目核心

> 9 道(4 连问 + 5 延伸题)。每题"短答 + 深度展开 + 可能追问"。面试前自己背 2 遍。

---

## Part 1 · 4 连问(基础必问)

### Q1. 你这个 agent 怎么决策下一步?

**短答**:LangGraph 的 ReAct——LLM 看 context(memory state + tool 描述 + 历史)选下一个 action,直到判断完成。

**深度展开**:
- Awake agent 用 `langgraph.prebuilt.create_react_agent`,system prompt 描述了 4 个 MCP tool 的处理流程
- 比如 `remember`:第一步 `search_archival` 找重复,第二步根据结果决定 merge/skip/new insert,第三步 `insert_archival_fact`
- 步数不固定,LLM 根据 observation 决定继续/终止
- Sleep agent 用 `StateGraph`(更结构化):节点 fixed pipeline,每个节点**内部**用 LLM 决策具体怎么做(promote 节点让 LLM 看候选 fact 决定升到哪个 core block)

**可能追问**:
- Q: 为啥 Awake prebuilt 但 Sleep 用 StateGraph?
  A: Awake 单一任务,prebuilt 够;Sleep 8 阶段固定 pipeline + 阶段内 LLM 决策,StateGraph 把 pipeline 显式化方便 reason about + 加 budget check
- Q: 那 plan phase 不就违反"固定 pipeline"了吗?
  A: Plan 给 LLM 看 state 决定后续跑哪些 phase,后续 node 都 check `if "consolidate" in state["plan"]`,不在就 pass through——pipeline 节点固定,但**执行哪些**是 LLM 决定

---

### Q2. agent 的 action space 多大?

**短答**:Awake 5 个内部 tool(load_core / search_archival / insert_archival / get_overview / forget_archival);Sleep 5 类 phase 操作(consolidate / promote / demote / resolve / reflect),每个 phase 内还有具体 fact-level action(MERGE / SKIP / KEEP_ALL 等)。

**深度展开**:
- 没用 Letta 完整 Tool Rules(`initial_tools` / `terminal_tools` / `children_tools`),MVP 简化为 system prompt 描述约束
- Sleep 各 phase 输出严格 JSON schema,parse 后 apply(`_safe_parse_json` 容忍 code fence)
- LLM 不让自由调任意 SQL —— 所有 mutation 走 `mneme.memory.store` 的限定 API

**可能追问**:
- Q: 不限制 LLM 调任意 tool 会不会越界?
  A: Awake system prompt 显式禁止改 core blocks;真要试,store 层抛 `PermissionError`;最后 DB `last_writer` 字段第三道防线
- Q: LLM 输出非 JSON 怎么办?
  A: `_safe_parse_json` 返回 `{"_parse_error": ...}`,phase node 看到空 actions 自然 no-op,cycle 继续不爆

---

### Q3. 失败怎么 fallback?

**短答**:Awake 走 LangGraph 内置 error 处理(tool 异常被 catch,error message 回 LLM 让其重试);Sleep 整个 cycle 在 try/except 包裹,异常时 cleanup staging tables,main 完全不受影响。

**深度展开**:
- Awake:LangGraph ReAct 内置 retry / error injection;tool 调用失败时 error 回 LLM,LLM 自己决定 try again / 报告 / 换路径
- Sleep:
  - 每 node 入口 `_budget_ok(state)` 检查 deadline,超了 pass through
  - `run_sleep_cycle` 整体 try/except,异常 → `cleanup_staging()` drop staging tables → main 安全
  - 关键 invariant:Sleep 异常**永远不会**让 main inconsistent,因为只动 staging
- atomic_swap 在单 transaction 内,要么全成功要么全回滚

**可能追问**:
- Q: atomic_swap 中间挂了呢?
  A: 单 tx,要么 commit 要么 rollback;真挂了 main 还是旧 main,staging 残留下次 cycle 起始 drop
- Q: APScheduler 多次 trigger 堆积?
  A: `max_instances=1` + `coalesce=True`,跨 trigger 还有 `_cycle_running` flag

---

### Q4. 跑了 20 步没结果咋办?

**短答**:Sleep cycle 有 wall-time budget(默认 5 min),每 phase node 入口 check deadline,超了直接跳到 swap;Awake 单次 MCP 请求由 LangGraph 自带 step limit 控制。

**深度展开**:
- Sleep: `settings.sleep_max_wall_time_seconds=300`,deadline 存 state 里,每 node 一开始 check
- Token budget 没强制(MVP 简化,Day 05+ 加 per-phase token cap)
- 单次 phase LLM 卡住 / 死循环 → APScheduler `max_instances=1` + `coalesce` 防堆积
- Awake:每次 MCP request 一次 ReAct,默认 LangGraph 自带 step limit(很大,够用)

**可能追问**:
- Q: token budget 没强制不会爆吗?
  A: DeepSeek 单次 chat context 64K,5 phase × 单 phase 几 K token,远低于;但 archival 巨多时 promote 候选会爆,Day 05+ 加 per-phase token cap

---

## Part 2 · 5 道延伸题(高质量加分)

### Q5. 为啥不直接用 mem0 / Letta SDK?自己造轮子?

**短答**:简历项目要展示**工程能力**,不是 import 能力。**核心机制自己写**才能聊得透;基础设施(SQLAlchemy / FastAPI / LangGraph / MCP SDK)直接用,这是行业惯例。

**深度展开**:
- 项目 70% 是 `pip install` 现成;30% 是核心业务(memory schema / Sleep agent / staging swap / system prompts)
- 那 30% 正好是面试官追问的部分。如果 fork mem0,被问到 "consolidation 算法怎么 trade-off" 答不上
- 反过来 SQLAlchemy / pgvector 直接用,没人会问 "为啥不自己写 ORM"
- Letta 是 Python framework,我借鉴 paper + 源码 idea,**实现成符合 Claude Code 集成的 MCP service**

**可能追问**:
- Q: mem0 比你这个成熟吧?
  A: 是。mem0 是产品,我这个是 demo + 简历项目。生产场景上 mem0,学习/展示工程能力上自己实现

---

### Q6. Sleep-time compute 跟普通 RAG memory 的区别?

**短答**:RAG 是 **read-time** scaling(检索增强 prompt);sleep-time 是 **write-time** scaling(后台用 compute 重组记忆)。Letta paper 数据 +13~18% 准确率 + ~5x compute 节省。

**深度展开**:
- RAG 只在用户问问题时检索 + 灌进 context,memory 是 raw / unstructured
- Sleep-time:agent idle 时主动做 reflection,把零散 fact 合并、提升、删除、解决矛盾,memory 是 **actively curated**
- Letta paper(arxiv 2504.13171):Stateful GSM-Symbolic +13%,Stateful AIME +18%
- mneme 把这个 idea 工程化到 Claude Code:Awake 写 archival,Sleep 提升到 core,使下次 recall 命中率更高 + memory 更整洁

**可能追问**:
- Q: mneme 的 archival_facts + 检索本质不还是 RAG 吗?
  A: Archival 检索确实是 RAG,但 mneme 的核心创新是 **core_blocks**(structured user profile,主动维护)+ Sleep agent 做 active curation,这是 RAG 没有的"agentic memory"层

---

### Q7. 并发安全 staging swap 跟纯 lock 的 trade-off?

**短答**:Staging swap 让 Sleep **不阻塞 Awake**(关键),代价是 Awake 在 Sleep 期间的 UPDATE 可能丢失(MVP 接受;Day 05+ 加 row-level merge)。纯 lock 简单可靠但 Sleep 会卡住 Awake,违背"做梦"的初心。

**深度展开**:
- 纯 lock(SELECT FOR UPDATE / advisory lock):Sleep 5 min 期间 Awake 全部卡住,违背 Letta paper "anytime fashion"(主 agent 应该能随时读 memory)
- Staging swap:Sleep 跑期间 Awake 完全不受影响(读写主表)
- 代价:Sleep 完成 swap 时,Awake 期间对主表的 INSERT 通过 `created_at > snapshot_ts` 合并到 staging;但 Awake 的 UPDATE(如 `mark_archival_used` 改 `use_count`)在被 Sleep 改过的 row 上会丢
- MVP 接受这个 trade-off,因为:Awake 主要 INSERT,Sleep 改的 row 不多,实际冲突很少
- Day 05+:row-level merge by version 字段 / last_updated timestamp

**可能追问**:
- Q: Postgres logical replication / CDC 能解决吗?
  A: 可以但 over-engineering for MVP。Day 05+ 真冲突高频再上
- Q: 为啥不用 PG advisory lock 简化?
  A: 同上,blocking 太重

---

### Q8. LLM-driven memory writes 和 backend CRUD 的根本区别?

**短答**:LLM-driven 是 LLM 自己 reason "该不该记 / 该记啥" 然后调 tool 写;backend CRUD 是固定路由,前端只是"使唤"后端。前者才算 agent,后者是 LLM 包装数据库前端。

**深度展开**:
- backend CRUD 模式:用户输入 → 后端规则提取 → 写入。LLM 只是格式化层
- LLM-driven:Claude Code 跟用户聊天,LLM 自己判断"哦,这是用户偏好,该 remember";调 `remember` 是 LLM 的 **autonomous decision**
- mneme 走后者:`remember` tool 的 docstring 写明"only for user-personal facts",LLM 看到合适的 fact 自己调
- 反例:如果 mneme 提供 `POST /api/preference` 让前端代码主动调,那 LLM 只是"被使唤"的,不算 agent

**可能追问**:
- Q: LLM 总会忘记调或者乱调吧?
  A: 是,这是真 risk。MVP 缓解:`remember` 的 tool docstring 写清规则(LLM 读 docstring 决定调用);`confidence` 字段让 LLM 表达不确定性;Sleep agent 定期清理 low-confidence

---

### Q9. mneme 怎么扩展到 multi-user / 接其他 MCP host?

**短答**:Multi-user 加 `user_id` 字段到所有表 + auth middleware;接其他 host **不用改任何代码**——MCP 协议本身就是 host-agnostic 的。

**深度展开**:
- MVP 单用户:`config.py:user_id="userjyx"` 写死,schema 没 user_id 列
- Multi-user 改动:
  1. schema 所有表加 `user_id TEXT NOT NULL` + index
  2. `memory.store` 所有查询/写入加 user_id filter
  3. MCP 层从 request header / JWT 解析 user_id 注入 context
  4. Sleep agent 改 per-user cycle(或全局 cycle 内 partition by user)
- 接 Cursor / Cline:MCP 是协议标准,host 那边配 mneme endpoint 就能用,mneme 完全不知道是谁在调

**可能追问**:
- Q: Sleep agent 跨 user 怎么 promote(怕 A 的 fact 进 B 的 core)?
  A: 每个 user 独立 cycle,Sleep run 时 partition by user;或者一个 cycle 内每 phase 按 user 分组处理

---

## Part 3 · 现场 demo cue cards

每个 cue 5-10 词,演示时一眼能看到知道说啥(配合 `docs/DEMO.md`):

1. "全新 session,认识我"
2. "实时 remember,DB 立刻看"
3. "切 project,记忆跨过去"
4. "Sleep cycle,reflection 看人话"
5. "架构图,Letta paper,三道保险"

---

## Part 4 · 应对 "这就是个数据库 + LLM"

**应对**:

> "如果只看 Awake 是,但 Sleep agent 是**无外部触发**的 autonomous loop——LLM 自己决定 plan / 自己决定哪些 fact 升级 / 自己解决矛盾,这部分跟数据库没关系,是 Letta paper sleep-time compute 的工程化实现。"

→ 主动展示研究背景,把对话拉到你最强的话题。

可以加一句:
> "可以看 docs/research-notes/letta-sleep-time-paper-notes.md,我 fetch 了 paper 的 blog 验证了机制,然后 fetch 了 letta/agent.py 源码确认 LLM-driven memory writes 是 Letta 的核心范式。"

---

## Part 5 · 应对 "为啥用 DeepSeek 不用 Claude"

**应对**:

> "学生项目成本约束。我手头有 DeepSeek 额度,Claude/GPT 跑 5-10 步 ReAct chain 一天可能 $5-20,DeepSeek 同等用量 $1 左右,差 10 倍。"
>
> "DeepSeek-chat tool calling 在 V3 后已经成熟,可以跑 5-step ReAct;但复杂 chain(8 phase Sleep cycle)上 DeepSeek 可能在 prompt engineering 上更费心。Demo 录制时如果质感需要可以临时切 Claude——代码层零改动,改一行 `.env` 就行。"

加分:
> "这其实是个有趣的 design decision——架构和 prompt 调到 DeepSeek 能跑的程度,反过来证明系统 robust。"

---

## Part 6 · 应对 "这个项目能商业化吗"

**应对**:

> "MVP 自用 + 简历。但赛道是真的——mem0 / Zep / Cognee / Letta 都在做 memory-as-a-service 这块。我做这个项目主要展示**工程能力**,生产化需要 multi-user / 隐私 / 计费 / SLA 等。"

加分:
> "如果商业化,可能切入点是 enterprise 内部 agent(HR onboarding agent / customer support agent),这些场景 memory infrastructure 很有价值——比直接做开发者工具好商业化。"

---

## Part 7 · 自我介绍 elevator(30s)

> "我是 Java backend 实习生(thunderbit),最近为校招做了一个 mneme 项目——给 Claude Code 装跨项目长期记忆服务。严格按 Letta sleep-time compute paper 设计,Awake/Sleep 双 agent 架构。代码 ~2100 行 Python,Stack: FastAPI + LangGraph + PostgreSQL + pgvector + MCP 协议。可以现场 demo,也可以白板讲架构。"
