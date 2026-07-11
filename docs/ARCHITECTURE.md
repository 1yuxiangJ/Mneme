# mneme 架构 + 流程(带术语注释)

> 这份文档**0 上下文也能看懂** mneme 怎么搭起来、Awake 怎么走、Sleep 怎么走、关键术语都是啥。给后来人(包括未来的你自己)用。
>
> 想看更深的工程决策:`docs/PLAN.md`(17 节总方案)+ `docs/DECISIONS.md`(Q1-Q14)。
> 想看代码:`src/mneme/`。

---

## 1. 它解决什么问题(业务背景)

用 Claude Code 写代码时,它**跨 session**(session = 一次对话窗口,关掉就消失)记不住"你这个人"——你的偏好(Ruff 不用 Black)、习惯(先写测试)、跨项目教训(`asyncio.gather` 别嵌 for loop)。

Claude Code 自带 `CLAUDE.md`(每个 project 根目录可放的 markdown,启动时自动读)和 **auto memory**(它自己写的 markdown,放在 `~/.claude/projects/.../memory/` 下),但这俩是**按 project 分**的——切到别的 project,你"这个人"的信息又得从头讲。

**mneme 就是补这个空白**:一个独立服务,记跨 project 的"用户画像",通过 MCP 协议给 Claude Code 当外置长期记忆。

> **MCP**(Model Context Protocol):Anthropic 2024 年提的协议。让 AI host(像 Claude Code 这种"装 LLM 的客户端")能调外部 server 暴露的 tool。本质是"AI 的 USB-C 接口"。

---

## 2. 整体架构(俯瞰)

```
┌─────────────────────────────────────────────┐
│  Claude Code (MCP host)                     │
│  ── 你跟它聊天的客户端                       │
└──────────────────┬──────────────────────────┘
                   │ HTTP(MCP 协议)
                   │ http://localhost:8000/mcp
                   ▼
┌─────────────────────────────────────────────┐
│  mneme service (跑在你电脑上)                │
│                                              │
│   ┌──────────────┐    ┌─────────────────┐   │
│   │ Awake Agent  │    │ Sleep Agent     │   │
│   │ 响应式        │    │ 后台自主         │   │
│   │ "做客服的"    │    │ "做梦整理的"    │   │
│   └──────┬───────┘    └────────┬────────┘   │
│          │                     │             │
│          └─────────┬───────────┘             │
│                    ▼                          │
│         ┌──────────────────────┐             │
│         │  PostgreSQL +        │             │
│         │  pgvector            │             │
│         │  (存所有 memory)      │             │
│         └──────────────────────┘             │
└─────────────────────────────────────────────┘
```

> **Awake / Sleep**:两个 agent。Awake 在 Claude Code 调它时才跑(像饭店服务员,有客人才上桌);Sleep 是后台 cron,平时不做事,空闲就开工整理 memory(像保洁,客人散了开始打扫)。
>
> **agent**(在 AI 领域):LLM 在循环里用 tool,自己决定下一步,直到判断"做完了"。区别于 **workflow**(代码写死步骤,LLM 只是其中一步)。
>
> **PostgreSQL**:Postgres,开源关系型数据库,业界标准之一。
>
> **pgvector**:Postgres 的一个 **extension**(扩展插件)。给它加了 `vector` 类型 + 向量距离计算。让 SQL 能直接做"找最相似的向量"。

---

## 3. 三个角色的关系

### 3.1 Claude Code(你坐在它前面的客户端)

它是 **MCP host**——一个支持 MCP 协议的客户端。你跟它对话,它内部跑 Claude/GPT,需要某些"超能力"时调 MCP server(我们的 mneme)。

它**不知道** mneme 内部架构,只知道 mneme 暴露了 4 个 tool:`remember` / `recall` / `list_memory` / `forget`。

### 3.1.1 Host-side 主动记忆策略

`remember` 是否被调用,第一判断发生在 **Claude Code host 端 LLM**。Mneme server 只能通过 MCP tool description 告诉它"这个工具能做什么";如果 host 端没有明确行为指令,模型通常会比较保守,只有用户说"记一下"时才调用 `remember`。

因此本机在 `/Users/mac/.claude/CLAUDE.md` 里增加了全局 Mneme 记忆规则:

- 不要等用户明确说"记住"。
- 遇到长期稳定、跨会话有用的用户事实时主动调用 `remember`。
- 范围包括工作学习,也包括长期兴趣、娱乐偏好、生活习惯、放松方式。
- 临时状态、当天计划、短期情绪、一次性事件不记。
- recent/temporary 信息先追问确认是否长期稳定。
- 敏感信息保存前先确认。
- 主动写入后给用户一个轻量确认,例如"我已记住:xxx。",避免静默写入。

这层规则和 MCP tool description 分工不同:

| 层 | 作用 |
|---|---|
| `/Users/mac/.claude/CLAUDE.md` | 告诉 Claude Code **什么时候应该主动用记忆工具** |
| `mcp_server.py` tool docstring | 告诉 Claude Code **remember 工具适合存什么、不适合存什么** |
| `awake/agent.py` system prompt | Mneme 内部接到 remember 后,负责去重、落库和边界约束 |

### 3.2 Awake Agent("接电话的")

收到 Claude Code 的 MCP 请求 → 内部跑一个 LangGraph ReAct loop → 处理 → 返回结果。

> **LangGraph**:Python 库,用来组织 agent 的多步逻辑。提供两种用法:
> - `create_react_agent`:一行起 ReAct agent
> - `StateGraph`:自己画状态机(节点 + 边)
>
> mneme 的 Awake 用前者,Sleep 用后者。

> **ReAct**:Reason + Act + Observe 的循环。LLM 先 reason(想)选个 tool,Act(执行 tool),拿到 Observe(结果),再循环。直到 LLM 说"完事了"。

### 3.3 Sleep Agent("做梦的")

跑在 APScheduler 后台。规则:
- 30 分钟没人调 Awake → 触发一次
- 每天凌晨 3 点 → 强制跑一次(兜底)

干啥:在 idle 时整理 memory(合并重复 / 升级常用 / 删除过期 / 解决矛盾 / 刷新 core / 写 reflection 一段"about user")。

> **APScheduler**:Python 定时任务库。能用 cron 表达式(`0 3 * * *` = 每天 03:00)或 interval(每 60 秒一次)触发函数。
>
> **idle**(空闲):没人在用。我们用 "上次 Awake 被调用时间 + 30 min" 判断。

### 3.4 4 个 MCP tool 详解(暴露给 Claude Code 的)

这 4 个 tool 是 mneme 跟 Claude Code 唯一的接口。`mcp_server.py` 里注册,签名固定。

#### `remember(content, tags=None, confidence=2, stability="long_term", salience=2)`

**何时被调**:Claude Code 的 LLM 在对话中**自己判断**"用户透露了关于他这个人的事实",主动调用。**不是用户喊"记一下"**——是 LLM 自主决策(LLM-driven memory writes,Letta paper 核心范式)。

例 1:你说"我决定以后所有项目都用 Ruff" → LLM 内部判断这是 cross-project 偏好 → 调 `remember("user prefers Ruff", ["preference", "tooling"], 3, "long_term", 3)`

例 2:你说"足球、游戏、刷 B 站/抖音基本是我长期的放松方式" → LLM 内部判断这是稳定生活偏好 → 调 `remember("user relaxes through football, games, Bilibili, and Douyin", ["lifestyle", "hobby", "entertainment"], 3, "long_term", 3)`

**应该记的范围**:关于用户这个人的长期稳定事实,不只限工作学习。包括身份、目标、技能、沟通偏好、工作/学习习惯、长期兴趣爱好、娱乐偏好、生活习惯、放松方式、产品/审美偏好、稳定喜欢/不喜欢。

**不应该记的范围**:临时状态、当天计划、一次性事件、短期情绪、项目内部事实。比如"今天有点累"不记;"最近游戏机不在身边"默认不记,除非用户确认这是长期模式。

**mneme 内部**:MCP tool 先把写入意图同步写入 `memory_write_jobs`;提交成功后快速返回 `accepted + job_id`;后台 worker 再复用 Awake agent ReAct → 先 `search_archival` 去重 → 没重复就 `insert_archival_fact` → 写 `memory_ops_log`

**返回**:`{"status": "accepted", "mode": "durable_async", "operation": "remember", "job_id": 42}`

**为什么异步但要 durable**:`remember` 是写类操作,Claude Code 当前回答通常不依赖 fact_id。同步等待会把 LLM ReAct + embedding + DB 写入的 2-5 秒延迟叠到用户体验上。Mneme 选择写异步、读同步:`remember` / `forget` 后台处理,`recall` / `list_memory` 同步返回可用结果。但 `accepted` 不能只代表"内存任务已创建",否则进程崩溃会丢消息;现在它代表"写入意图已落 PostgreSQL job 表"。

**参数**:
- `content`:要记的事实(自然语言)
- `tags`:标签数组(给后续 demote/promote 筛选用)
- `confidence`:事实确定性,不是 LLM 自报概率,也不是"这条记忆重要不重要"。
- `stability`:时间跨度,区分长期稳定 / 阶段性 / 临时信息。
- `salience`:未来有用程度,给 Sleep promote/demote/reflect 做价值排序。

三类记忆信号拆开后,避免所有"用户明确说过"都被打成 `confidence=3`:

| 字段 | 取值 | 语义 | 例子 |
|---|---|---|
| `confidence` | 1/2/3 | 事实确定性:推断 / 部分确认 / 用户明确说过 | "用户明确说自己喜欢足球" → 3 |
| `stability` | `long_term` / `stage` / `temporary` | 时间跨度:长期画像 / 当前阶段 / 短期状态 | "秋招优先冲大厂" → stage |
| `salience` | 1/2/3 | 未来协作价值:低 / 中 / 高 | "偏好直接具体解释" → 3 |

如果一句话里混合长期事实和临时细节,应该拆开保存成多条不同 `stability/salience` 的记忆,或者跳过临时细节。不能把整句话统一打成一条 `confidence=3, stability=long_term, salience=3` 的高价值长期记忆。

#### `recall(query, limit=5)`

**何时被调**:LLM 接到你提问,需要"查我之前知道用户什么"时调。

例:你问"推荐个 Python web 框架" → LLM 调 `recall("Python web framework preferences")` 看你有没有偏好

**mneme 内部**:Awake agent ReAct → `load_core` 拿 5 个 core block 概览 → `search_archival` 向量检索 top-K → 综合返回

**返回**:`{"core_blocks": [...], "archival": [{id, content, distance}, ...]}`

**side-effect**:被返回的 archival 自动 `use_count += 1` + `last_used_at = now()`,给 Sleep promote 提供信号。

#### `list_memory()`(无参数)

**何时被调**:**新 session 开始第一次跟用户对话时**,LLM 想"知道用户是谁",一次性看 overview。

**mneme 内部**:MCP server direct DB fast path → `get_memory_overview` + `list_archival_facts`。

这里**不走 Awake ReAct / DeepSeek**。原因是 `list_memory` 是确定性只读概览,不需要 LLM 推理;如果为了"统一架构"强行绕 Awake,DeepSeek 或代理环境一抖,新 session 反而拿不到用户画像。当前设计把它作为可靠的启动读路径。

**返回**:
```json
{
  "status": "ok",
  "mode": "direct_db",
  "core_blocks": [
    {"label": "background", "value": "Java backend intern...", "version": 3},
    ...
  ],
  "archival_total": 47,
  "archival_facts_limit": 20,
  "archival_facts": [
    {"id": 2, "content": "Java backend developer...", "tags": ["career"]}
  ]
}
```

#### `forget(fact_id, reason)`

**何时被调**:LLM 发现某条 archival 是错的 / 过时的,主动删。

例:你说"我现在不用 Black 了,改用 Ruff" → LLM 先 `recall` 找到 id=37 "user uses Black" → 调 `forget(37, "user switched from Black to Ruff")`

**mneme 内部**:MCP tool 先同步写入 `memory_write_jobs`;后台 worker 复用 Awake agent ReAct → `forget_archival` → 软删除(`is_deleted=true`)+ ops log

**返回**:`{"status": "accepted", "mode": "durable_async", "operation": "forget", "job_id": 43}`

**软删不真删**:数据保留可恢复;search/recall 自动 filter `is_deleted=false`。

### 3.5 两层 tool 架构(MCP tool ↔ Awake 内部 @tool)

mneme 有**两层 tool**——这是个**架构分层**的设计:

```
┌────────────────────────────────────────────────┐
│  Layer 1: MCP tool(给 Claude Code 用)         │
│  remember / recall / list_memory / forget      │
│  ── "业务语义" 层                              │
└──────────────────┬─────────────────────────────┘
                   │  Awake agent ReAct loop
                   │  LLM 看 system prompt
                   │  决定调哪些内部 @tool
                   ▼
┌────────────────────────────────────────────────┐
│  Layer 2: Awake 内部 @tool                      │
│  load_core / search_archival /                  │
│  insert_archival_fact / get_overview /          │
│  forget_archival                                │
│  ── "原子操作" 层                              │
└──────────────────┬─────────────────────────────┘
                   │  直接函数调用
                   ▼
┌────────────────────────────────────────────────┐
│  Layer 3: memory/store.py(DB CRUD + 权限自检) │
└────────────────────────────────────────────────┘
```

**为什么不让 MCP tool 直接调 store.py?**

如果 MCP `remember` 直接调 `store.insert_archival`——中间没 LLM——那就是"LLM 包装的 CRUD",失去 agent 性。让 LLM 在 Awake 内部跑 ReAct,**才能根据 observation 自适应**:

- 事实明确 + 短文本 → LLM 可能跳过 search 直接 insert
- 低 confidence + 长文本 → 先 search 看有没有近似
- 检测到 dup → LLM 决定 skip / merge / 还是 insert

简单 case(`forget`)看起来是 1:1 多此一举,但**统一架构**有好处:未来想加复杂逻辑只改 prompt,不动代码。`list_memory` 是例外:它是新 session 的启动读路径,必须尽量稳定、低延迟、低成本,所以直接查 DB。

**4 个 MCP tool ↔ Awake 5 个内部 @tool 对应表**:

| MCP tool(Layer 1) | Awake 内部 @tool(Layer 2) | 关系 |
|---|---|---|
| `remember` | `memory_write_jobs` → worker → `search_archival` + `insert_archival_fact` | 1:多(LLM 决定怎么组合);MCP 层 durable 异步返回 |
| `recall` | `load_core` + `search_archival` | 1:多 |
| `list_memory` | 不走 Awake;MCP 层直读 DB | direct DB fast path |
| `forget` | `memory_write_jobs` → worker → `forget_archival` | 1:1(简单 case);MCP 层 durable 异步返回 |

**`forget` 完整四层调用链**(从你喊话到 SQL 落盘):

```
你说 "我现在不用 Black 了"
   ↓
Claude Code 的 LLM 判断 → 调 mcp__mneme__forget(37, "user switched")
   ↓
Layer 1: mcp_server.py:forget(fact_id=37, reason="...")
   ↓ 转 Awake agent
Awake LLM 看 system prompt → 决定调 forget_archival
   ↓
Layer 2: awake/tools.py:forget_archival(37, "user switched")
   ↓ 直接调函数
Layer 3: memory/store.py:soft_delete_archival(...)
   ↓ 真正的 DB 操作
Layer 4: UPDATE archival_facts SET is_deleted=true WHERE id=37
         INSERT INTO memory_ops_log (...)
```

**实际成本**(诚实):每次 ReAct = 至少 1 个 LLM call(几百 token,1-2 秒)。所以 Mneme 只让真正需要语义推理的 `remember` / `recall` / `forget` 走 Awake。`list_memory` 已改成 direct DB fast path,避免新 session 起手就依赖 DeepSeek。

---

## 4. 一次 `remember` 的完整流程(sequence diagram)

假设你跟 Claude Code 说"我喜欢 4 空格不用 tab"。

```
你 → Claude Code:"我喜欢 4 空格"
                  │
                  │ (Claude Code 的 LLM 内部判断:这是用户偏好,应该记下来)
                  ▼
Claude Code → mneme MCP server:
              remember(content="user prefers 4-space indent",
                       tags=["preference"], confidence=3,
                       stability="long_term", salience=3)
                                │
                                │ (mcp_server.py 收到 → enqueue durable job)
                                ▼
                       mark_awake_activity()  ← 重置 idle 计时器
                                │
                                ▼
                       INSERT INTO memory_write_jobs
                         (operation='remember', command=..., payload=...,
                          status='pending', dedupe_key=...)
                                │
                                ├── COMMIT 成功
                                │
                                ├── 立刻返回 {status: "accepted",
                                │           mode: "durable_async", job_id: 42}
                                │
                                ▼
                       memory worker claim job
                         SELECT ... FOR UPDATE SKIP LOCKED
                         status: pending → running
                                │
                                ▼
                       worker 调用 run_awake(command)
                                │
                                ▼
                       Awake Agent 启动 LangGraph ReAct
                                │
                                │ Round 1 (reason):
                                │   LLM 看 system prompt:
                                │   "我应该先 search 看有没有重复"
                                ▼
                       调 internal tool: search_archival(
                         "user prefers 4-space indent")
                                │
                                │ (Awake Agent 内部 @tool,不是 MCP tool)
                                ▼
                       memory/store.py:semantic_search_archival(...)
                                │
                                │ 1. 调 阿里通义 embedding API,
                                │    把 query 变成 1024 维向量
                                │    (同文本走进程内 cache,避免 remember 查重/入库重复计算)
                                │ 2. SQL: SELECT * FROM archival_facts
                                │         ORDER BY embedding <=> :vec
                                │         LIMIT 5
                                │ 3. pgvector 用 HNSW 索引秒级找最近邻
                                ▼
                       返回 [{id: 12, content: "...similar fact...",
                              distance: 0.4}]
                                │
                                │ Round 2 (reason + observe):
                                │   LLM 看到 distance=0.4
                                │   (不太相似,不算 duplicate)
                                │   → "插入新 archival"
                                ▼
                       调 internal tool: insert_archival_fact(...)
                                │
                                ▼
                       memory/store.py:insert_archival(...)
                                │
                                │ 1. 取 content embedding
                                │    (如果 search_archival 刚算过同文本,直接复用 cache)
                                │ 2. INSERT INTO archival_facts
                                │    (content, tags, confidence, embedding, ...)
                                │ 3. INSERT INTO memory_ops_log
                                │    (op_type='remember', actor='awake_agent', ...)
                                │ 4. COMMIT(同一个 transaction)
                                ▼
                       返回 fact_id=142
                                │
                                │ Round 3:
                                │   LLM 看到 success
                                │   → "task 完成了,返回 summary"
                                ▼
                       Awake Agent 返回:
                       {status: "ok", final_message: "Stored as fact 142", step_count: 6}
                                │
                                ▼
                       UPDATE memory_write_jobs
                         status='succeeded', result=...
              ◄─── 后台 worker 完成
```

**异步写入的代价**:Claude Code 收到 `accepted` 时,事实不一定已经落库。刚 `remember` 后立刻 `recall` 可能暂时查不到,这是最终一致性取舍。区别是:现在 `accepted` 前 job 已经提交到 PostgreSQL,所以 Mneme 进程在 worker 执行前崩溃,任务也不会凭空丢;重启后 worker 会继续处理 `pending` job。

**失败处理**:worker 失败会把 job 重新置为 `pending`,按 5s / 30s / 120s 简单退避重试,超过 `max_attempts=3` 后标记 `failed` 并记录 `last_error`。如果 worker 在 `running` 中崩溃,超过 `memory_write_job_stale_seconds` 后会被重置为 `pending`。

**Awake 防卡死**:Awake ReAct 显式限制 `recursion_limit=8`,LLM 单步 `timeout=20s, max_retries=1`,外层 `asyncio.wait_for(..., 45s)` 兜底。极端情况下返回 `status="timeout"` 而不是让 Claude Code 一直等。

> **embedding**(嵌入向量):把一段文本变成一串数字(mneme 用 1024 维,即 1024 个 float)。神经网络训出来的——意思相近的文本,向量在 1024 维空间也相近。
>
> 例:"prefers 4 spaces" vs "uses 4-space indent" 距离 0.05(几乎一样);"prefers FastAPI" 距离 0.8(无关)。

> **cosine distance**(余弦距离):衡量两个向量"角度差"。0 = 完全一样,1 = 完全无关,2 = 完全反向。pgvector 用 `<=>` 运算符算。

> **HNSW**(Hierarchical Navigable Small World):向量索引算法。普通 B-tree 不适合向量(按一维排序,向量是多维)。HNSW 用图结构,几毫秒内找到 K 个最近邻(approximate,实践够用)。

> **transaction**(事务):数据库的"原子操作单元"。一组 SQL 要么全成功要么全回滚。Awake 写入时把 INSERT archival + INSERT memory_ops_log 放一个 transaction;Sleep 写入时先累积 pending_ops,最后在 atomic swap 同一 transaction 里 flush 到 memory_ops_log。

---

## 5. 一次 `recall` 的流程(简版)

你新开 Claude Code session:"推荐 Python 框架"

```
Claude Code → mneme:recall(query="Python web framework preferences",
                            limit=5)
              │
              ▼
       Awake Agent ReAct:
              Round 1: 调 load_core() 看用户画像
                       → core_blocks: {
                           background: "Java backend intern...",
                           preferences: "FastAPI / async I/O", ...}
              Round 2: 调 search_archival(query)
                       → archival 里找语义相关的 5 条
              Round 3: 综合 core + archival → 返回结构化结果
              │
              ▼
Claude Code 综合 mneme 返回 + 你的当前问题 → 回答:
   "根据你之前的偏好,推荐 FastAPI:..."
```

---

## 6. Sleep cycle 完整流程(sequence trace + 真实例子)

> 跟 §4 同款风格,step-by-step 走完一次完整 cycle。
> **假设场景**:archival 已有 30 条,几个高频 fact(`use_count > 5`),你最后一次跟 Claude Code 对话后离开 30 分钟。

```
[T=0]      你最后一次调 Claude Code → mark_awake_activity() 重置 idle 计时
[T+30min]  没人调 Awake 30 分钟

[每 60s 跑] APScheduler 跑 _idle_tick()
   ▼ _idle_seconds() = 1820s ≥ 1800s threshold ✓
   ▼ _cycle_running = False(没在跑)→ 启动 cycle
   ▼
run_sleep_cycle():
   deadline = monotonic() + 300s  (5 min budget)
   init state = {deadline_ts, aborted: False, ...}
   ▼ LangGraph graph.ainvoke(init_state)
```

### Node 1: snapshot

**为啥**:Sleep cycle 可能跑 5 分钟,期间不能直接改 main(中间状态会让 Awake 看到不一致数据)。先复制一份 `*_staging` 副本,在副本上改。

**做啥**(SQL):
```sql
DROP TABLE IF EXISTS core_blocks_staging;
CREATE TABLE core_blocks_staging (LIKE core_blocks INCLUDING ALL);
INSERT INTO core_blocks_staging SELECT * FROM core_blocks;
-- archival_facts 同样三步
COMMIT;
```

**拿到**:`snapshot_ts = "2026-06-17 14:30:00"`(后面 swap 时用来合并"Awake 期间的新数据")

→ `state["snapshot_ts"] = ts`

---

### Node 2: plan ← LLM 决定本次跑哪些 phase(项目灵魂)

**为啥**:不是"固定 cron 跑所有 phase"——LLM 看当前 state 自己决定本次跑什么。这是 mneme "真 agent" 的核心(LLM-driven decision)。

**做啥**:
1. `summarize_state()` 拿 memory 当前状态(archival 数 / stale 数 / 高频 fact 数 / 当前 core blocks)
2. 喂 LLM `PLAN_PROMPT`,要求 JSON 输出

**LLM 输出例**:
```json
{
  "phases": ["consolidate", "promote", "core_refresh", "reflect"],
  "reason": "8 new archival since last cycle (dedup); 3 high-freq for promote; core may contain stale details; reflect always at end"
}
```

→ `state["plan"] = ["consolidate", "promote", "core_refresh", "reflect"]`

后续 `consolidate / promote / demote / resolve / reflect` 仍按 plan 决定是否执行。`core_refresh` 是例外:运行时会强制把它补进 plan,因为计划阶段没有足够证据判断 Core 是否过时。它每轮都进入检查,但如果上次 checkpoint 后没有相关变化,会在调 LLM 前快速跳过。

---

### Node 3: consolidate(在 plan 里 → 执行)

**为啥**:你在不同时间说同样的事,archival 里会出现近似 duplicate。Sleep 合并以减少噪音。

**做啥**:
1. SQL 找两两 cosine 距离 < 0.15 的 cluster
2. 把 cluster 喂 LLM 决定 MERGE / KEEP_ALL(LLM 看具体 content,不只看距离)
3. 应用决定到 staging

**例子**:
- SQL 找到 cluster:`[id=12 "I like 4-space", id=88 "user prefers 4-space indent"]`
- LLM 决定:
  ```json
  {"cluster_index": 0, "decision": "MERGE",
   "kept_id": 88, "discarded_ids": [12],
   "merged_content": "user prefers 4-space indentation",
   "reason": "id=88 wording is more precise"}
  ```
- 应用到 staging:
  ```sql
  UPDATE archival_facts_staging
    SET content='user prefers 4-space indentation'
    WHERE id = 88;
  UPDATE archival_facts_staging SET is_deleted = TRUE WHERE id = 12;
  ```
  同时生成一条 `pending_ops` 草稿:`op_type='sleep_consolidate'`。这条日志暂时只放在 StateGraph state 里,不写主 `memory_ops_log`。

---

### Node 4: promote ← 唯一改 core_blocks 的路径!

**为啥**:archival 里"被反复用 + 用户明确说过 + 长期稳定 + 未来有用"的 fact,才该提升到结构化的 core block,成为用户画像的固定一部分。**Sleep 是 core_blocks 的 sole writer**(Letta read-only primary)。

**做啥**:
1. SQL 找 `use_count >= 5 AND confidence >= 3 AND stability = 'long_term' AND salience >= 3` 的 archival
2. 把候选 + 当前 core_blocks 喂 LLM(LLM 要看 core 当前内容才能写新值)
3. LLM 决定哪些 PROMOTE / SKIP,PROMOTE 到哪个 core block,新 block 整段 value 是什么
4. 应用到 `core_blocks_staging`

**target block 分流规则**:
- `preferences`:喜欢/不喜欢、价值判断、优先级、选择倾向。
- `habits`:长期重复行为、生活/工作节奏、常见放松方式。
- 细颗粒生活事实(某个食物、某个游戏模式、设备一时在不在身边)默认留在 archival;只有它表达出更高层的长期模式时才概括进 core。

**例子**:
- 候选 archival:
  ```
  [id=88,  use_count=7,  conf=3, stability=long_term, salience=3, "user prefers 4-space indentation"]
  [id=199, use_count=12, conf=3, stability=long_term, salience=3, "user writes tests first"]
  [id=158, use_count=5,  conf=3, stability=stage,     salience=2, "user recently mainly plays CS2"]
  ```
- LLM 决定:
  ```json
  [
    {"fact_id": 88, "decision": "PROMOTE", "target_block": "preferences",
     "new_block_value": "User prefers Ruff over Black for Python formatting,
                         likes 4-space indentation, favors FastAPI for async APIs...",
     "reason": "stable code-style preference"},
    {"fact_id": 199, "decision": "PROMOTE", "target_block": "habits",
     "new_block_value": "User writes tests before implementation (TDD-leaning)...",
     "reason": "consistent workflow across projects"},
    {"fact_id": 158, "decision": "SKIP",
     "reason": "stage-specific leisure fact, not core user profile material"}
  ]
  ```
- 应用到 staging:
  ```sql
  UPDATE core_blocks_staging SET
    value = 'User prefers Ruff over Black...',
    version = version + 1,
    last_writer = 'sleep_agent',
    updated_at = now()
    WHERE label = 'preferences';
  -- 生成 pending op: op_type='sleep_promote', target_id='preferences'
  -- 同样处理 habits;SKIP 158
  ```

---

### Node 5: demote(在 plan 里 → 执行;不在 plan 里 → 跳过)

**为啥**:archival 是零散事实仓库,只增不清会越来越吵。Sleep 需要把"长期没被用到 + 低信号"的事实软删,降低 recall 噪音和后续 Sleep 的处理成本。

**注意**:`demote` 不是删 core block。core block 是高层用户画像,由 `promote` / `resolve` / `core_refresh` 修改;`demote` 当前只处理 `archival_facts_staging` 里的低价值 fact。

**做啥**:
1. SQL 找 stale candidates:长期没被 recall 用过,且 `confidence <= 1 OR stability='temporary' OR salience <= 1`,还没被软删的 archival
2. 把候选喂 LLM `DEMOTE_PROMPT`
3. LLM 对每条判断 `FORGET` / `KEEP`
4. 只对 `FORGET` 的 fact 在 staging 表里 `is_deleted = TRUE`
5. 生成 `pending_ops(op_type='sleep_demote')`

**例子**:
- 候选 archival:
  ```
  [id=31, confidence=1, stability=stage,     salience=1, last_used_at=120 days ago, "user might try Flask someday"]
  [id=44, confidence=2, stability=temporary, salience=1, last_used_at=110 days ago, "user's PS5 is currently away"]
  [id=88, confidence=3, stability=long_term, salience=3, last_used_at=140 days ago, "user prefers 4-space indentation"]
  ```
- LLM 决定:
  ```json
  {
    "actions": [
      {"fact_id": 31, "decision": "FORGET", "reason": "low-confidence tentative interest, never reused"},
      {"fact_id": 44, "decision": "FORGET", "reason": "temporary low-salience state, stale"},
      {"fact_id": 88, "decision": "KEEP", "reason": "confidence=3 facts must not be forgotten by demote"}
    ]
  }
  ```
- 应用到 staging:
  ```sql
  UPDATE archival_facts_staging
    SET is_deleted = TRUE
    WHERE id = 31;
  -- 生成 pending op: op_type='sleep_demote', target_kind='archival', target_id='31'
  ```

**保守规则**:
- `confidence=3` 永远不由 demote 删除
- `stability=long_term AND salience>=2` 的事实默认保守保留
- 有可能解释 core block 的 fact 不删
- 不确定就 `KEEP`
- 删除是软删,不是物理删除;`inspect_memory.py --include-deleted` 还能看见

→ `state["demote_actions"] = actions`

---

### Node 6: resolve(在 plan 里 → 执行;不在 plan 里 → 跳过)

**为啥**:长期记忆会出现冲突。比如早期 core 写"用户喜欢详细解释",后面又沉淀出"用户不喜欢冗长解释"。这两句话不一定真的矛盾,但如果 core block 里表达得互相打架,Claude Code 后续就会拿到混乱的用户画像。

**resolve 解决的是 core 层的语义冲突**,不是简单 duplicate。duplicate 归 `consolidate`,低价值遗忘归 `demote`,稳定偏好升级归 `promote`。

**做啥**:
1. 读取当前 5 个 `core_blocks_staging`
2. 读取最近 20 条 `memory_ops_log`,作为上下文
3. 喂 LLM `RESOLVE_PROMPT`,要求找 block 内部或 block 之间的真正逻辑冲突
4. LLM 输出需要修哪个 block,以及"完整的新 block value"
5. 应用到 `core_blocks_staging`,`version + 1`,`last_writer='sleep_agent'`
6. 生成 `pending_ops(op_type='sleep_resolve')`

**例子**:
- 当前 core blocks 片段:
  ```text
  preferences:
  User prefers very detailed explanations and likes broad conceptual background.

  habits:
  User dislikes vague or long-winded answers; prefers direct, concrete engineering explanations.
  ```
- LLM 判断:
  ```json
  {
    "contradictions": [
      {
        "blocks_involved": ["preferences", "habits"],
        "description": "preferences says broad detailed explanations, habits says direct concrete answers",
        "fix_block": "preferences",
        "new_block_value": "User prefers direct, concrete engineering explanations. Detail is useful when it clarifies trade-offs or implementation steps, but vague long-winded background should be avoided.",
        "reason": "newer repeated preference clarifies that detail is welcome only when actionable"
      }
    ]
  }
  ```
- 应用到 staging:
  ```sql
  UPDATE core_blocks_staging SET
    value = 'User prefers direct, concrete engineering explanations...',
    version = version + 1,
    last_writer = 'sleep_agent',
    updated_at = now()
    WHERE label = 'preferences';
  -- 生成 pending op: op_type='sleep_resolve', target_kind='core', target_id='preferences'
  ```

**当前实现细节**:resolve 阶段生成独立 `sleep_resolve` pending op。swap 成功后才写入主 `memory_ops_log`,这样审计日志能一眼区分"合并重复事实"和"解决 core 冲突"。

**保守规则**:
- 只修真正逻辑冲突,不要把风格差异当冲突
- `new_block_value` 必须是完整 block,不是 diff
- 只能 Sleep 写 core,Awake 没有这条路径
- 不确定就输出 `{"contradictions": []}`

→ `state["contradictions"] = contradictions`

**为什么 resolve 只处理 core 冲突,不直接处理 archival 冲突?**

因为两层 memory 的一致性要求不一样:

| 冲突位置 | 当前怎么处理 | 原因 |
|---|---|---|
| archival vs archival | 不由 `resolve` 直接处理,可能被 `consolidate` / `demote` / `promote` 间接处理 | archival 是原始事实仓库,允许保留事实演化痕迹;看似冲突可能只是时间变化或语境不同 |
| archival vs core | 主要在 `promote` 时综合处理 | promote 会同时看候选 archival 和当前 core,可以把新事实写成更准确的 core 表达 |
| core vs core | 由 `resolve` 主动审计 | core 是 Claude Code 会直接读取的用户画像,如果互相打架会直接污染回答 |
| core block 内部自相矛盾 | 由 `resolve` 主动审计 | 没有新 archival 触发同一 block 更新时,这种存量矛盾可能长期残留 |

换句话说:

- `consolidate`:压缩 archival 里的重复事实
- `demote`:软删 archival 里的低价值旧事实
- `promote`:把 archival 里的稳定事实综合进 core
- `resolve`:检查 core 自己是否自洽
- `core_refresh`:清理 core 里过期、过细、缺少当前 archival 支撑的内容

archival 层不强求全局一致,因为它保留的是"用户曾经表达过什么";core 层必须自洽,因为它代表"系统当前相信的用户画像"。

后续如果要专门处理 archival 冲突,可以新增 `reconcile_archival` phase,做 supersede 标记、降低旧 fact confidence、补时间范围,而不是简单删除其中一条。

---

### Node 7: core_refresh ← 清理 core 过期 / 过细内容

**为啥**:`demote` 只清 archival,不能清 core。core 是整段用户画像,如果曾经写入了阶段性事实或过细生活细节,仅靠 archival demote 不会自动删除这些文本。`core_refresh` 专门维护 core 质量,避免 core 变成杂项事实列表。

**做啥**:
1. 读取 `core_blocks_staging`
2. 查询上一条 `sleep_core_refresh/__checkpoint__` 之后的相关 ops,并合并本轮尚未 swap 的 pending ops
3. 如果 Core 为空,或已有 checkpoint 且没有相关变化,直接跳过 LLM
4. active fact 数 `<= 200` 时,加载全部 active facts
5. active fact 数 `> 200` 时,对每个非空 Core 做语义 Top 8,再合并上次 checkpoint 后变更的 facts 和全局高信号 Top 10,按 fact id 去重
6. 喂 LLM `CORE_REFRESH_PROMPT`,要求判断每个 Core 是 `REFRESH` 还是 `KEEP`
7. 只对 `REFRESH` 的 block 写入完整新 value,`version + 1`,`last_writer='sleep_agent'`
8. 无论本轮是修改还是全部 `KEEP`,都生成一条 `target_id='__checkpoint__'` 的 pending op;只有最终 swap 成功才会写入主日志

**为什么不只加载新增 fact?**

新增 fact 只能帮助发现"被新事实覆盖"的过期内容,但不能判断 Core 里的老内容是否仍然合理。小数据时全量读取避免证据漏失;超过 200 条后,全局 Top-K 容易被单一主题占满,所以改为“每个 Core 分别找证据 + 保留全部增量变化 + 少量全局高信号”。

三类输入的分工:

| 输入 | 作用 |
|---|---|
| 当前 core | 被审查、可能被重写的对象 |
| active archival evidence | `<=200` 时全量;`>200` 时按 Core 语义相关性、增量变化和全局高信号组合取证 |
| ops since checkpoint | 说明上次成功检查后发生了什么,不再用容易被批量写入挤掉的“最新 20 条” |

**为什么要看 ops log?**

`memory_ops_log` 不是事实来源,而是变更索引。Refresh 通过 `__checkpoint__` 记住上次已审查到的 op id,下次只读之后的 remember / forget / consolidate / promote / demote / resolve / refresh 变化。本轮尚未写主日志的 pending ops 也会一起提供给 LLM。这既防止批量 remember 挤掉关键历史,也避免无变化时重复付费调用。

**它会清什么**:
- 已经过期的阶段性内容
- 过细、不该常驻 core 的生活细节
- 被更新事实覆盖的旧表达
- 缺少 active archival 支撑的低价值内容

**它不会清什么**:
- 长期高显著偏好
- 沟通偏好、职业优先级、稳定习惯
- 只是暂时没被 recall 命中的核心画像

→ `state["core_refresh_actions"] = actions`

---

### Node 8: reflect ← 输出一段 "about user" 摘要

**为啥**:产出自然语言"about user"段落,供人 review(看 Sleep 整理得对不对),也给后续 cycle 提供 context。

**做啥**:
1. 拿(已被 promote 改过的)core_blocks + 高 conf archival 5 条
2. 喂 LLM `REFLECT_PROMPT`,要求 2-4 句话
3. 生成 `pending_ops(op_type='sleep_reflect')`

**LLM 输出例**:
> "User is a Java backend intern at Thunderbit, job-hunting for Java backend and AI agent roles. Prefers Ruff and 4-space indent. Writes tests before implementation. Recently learned to avoid nested asyncio.gather in for-loops."

---

### Node 9: swap ← atomic 切换 staging → main

**为啥**:把已被 Sleep 改过的 staging 切换成新 main。**原子**切换避免 Awake 看到"半成品"状态。

#### 先看懂两版数据

Sleep 运行期间,同一类记忆有两个版本:

```text
archival_facts          = 正式主表 A,Awake 持续读写
archival_facts_staging  = Sleep 工作副本 B,Sleep 在这里整理

core_blocks             = 正式 Core A,Awake 只读
core_blocks_staging     = Sleep 整理后的 Core B
```

Node 9 不是直接把 B 盖到 A 上,而是先把 Sleep 期间 A 里发生的实时变化合并进 B,再交换 A / B 的表名。全部动作在同一个 PostgreSQL transaction 中完成。

#### 第一步:快速拿锁,冻结 Archival 写入

`lock_timeout=500ms` 限制的是**等锁时间**,不是整个 swap 的运行时间。500ms 内拿不到锁就放弃本轮,避免 swap 在长查询后面排队并堵住新请求。

拿到 `SHARE ROW EXCLUSIVE` 后:

```text
普通 SELECT              -> 仍可继续
INSERT / UPDATE / DELETE -> 暂时等待
```

这会关闭“合并刚完成,Awake 又写一次,然后立刻 swap”的尾部竞态窗口。

#### 第二步:把 Awake 新增的 Fact 补进 B

例如 snapshot 时两边都只有 `#1 / #2`,Sleep 期间 Awake 在主表 remember 了 `#3`:

```text
主表 A: #1 #2 #3
Sleep B: #1 #2
```

Node 9 用 `created_at > snapshot_ts` 找到 `#3`,补入 B。`ON CONFLICT (id) DO NOTHING` 让保守多捞的行可以安全忽略重复 ID。

#### 第三步:合并旧 Fact 的并发字段

对 snapshot 时已经存在的 Fact,Sleep 和 Awake 可能修改了不同字段:

```text
主表 A: content="用户喜欢足球",       use_count=6
Sleep B: content="用户长期关注足球运动", use_count=5
```

如果整行取 A,Sleep 的语义整理会丢;整行取 B,Awake 的 recall 计数会丢。因此按字段所有权合并:

| 字段 | 最终取值 |
|---|---|
| `content/tags/confidence/stability/salience/embedding` | Sleep 在 B 里的语义整理结果 |
| `use_count/last_used_at` | A / B 中更大、更新的访问统计 |
| `is_deleted` | A / B 做 OR,任意一边 forget / demote 都保留删除 |

上例的最终结果是:

```text
content="用户长期关注足球运动"
use_count=6
```

#### 第四步:用三步 RENAME 交换 A / B

`archival_facts_staging` 不能直接改名为 `archival_facts`,因为这个名字正被 A 占用。所以要经过一个临时名:

```text
初始:
  archival_facts          = A
  archival_facts_staging  = B

1. archival_facts -> archival_facts_tmp_swap
2. archival_facts_staging -> archival_facts
3. archival_facts_tmp_swap -> archival_facts_staging

结果:
  archival_facts          = B  (新主表)
  archival_facts_staging  = A  (旧主表)
```

`core_blocks` / `core_blocks_staging` 也执行同样的三步。RENAME 会短暂需要 `ACCESS EXCLUSIVE LOCK`,但 PostgreSQL 的 DDL 在 transaction 中也是原子的:Awake 只会看到提交前的 A,或提交后的 B,不会看到中间改名状态。

#### 第五步:清空旧主表

换名后,`*_staging` 指向的已经是旧 A。Node 9 对它执行 `TRUNCATE`,保留空表结构。因此成功 Sleep 后在 DataGrip 里看到空 staging 表是正常现象,不是脏数据。

#### 第六步:把 pending ops 与 swap 一起提交

Promote / Demote / Resolve / Refresh / Reflect 产生的日志在前面都只是内存草稿。Node 9 才把它们写入 `memory_ops_log`,并和表名切换使用同一个 transaction。

```text
全部成功 -> 新主表 + Sleep 日志 + Refresh checkpoint 一起生效
任意失败 -> 整个 transaction 回滚,仍使用旧主表,日志和 checkpoint 都不写
```

所以 Node 9 是整个 Sleep cycle 的**真正提交点**:前面所有 phase 只是在 staging 中准备候选结果,swap 成功后才影响正式记忆。

#### 对照实际 SQL

下面的 SQL 就是上述六步的代码形式,全部位于同一个 transaction:

```sql
BEGIN TRANSACTION;

-- swap 会拿 ACCESS EXCLUSIVE LOCK;拿不到锁就快速失败,避免队头阻塞在线请求
SELECT set_config('lock_timeout', '500ms', true);

-- (a) 短暂冻结 archival 写入,但普通 SELECT 仍可继续
--     后面 RENAME 时才会升级为 ACCESS EXCLUSIVE LOCK
LOCK TABLE archival_facts IN SHARE ROW EXCLUSIVE MODE;

-- (b) 把 Awake 期间(snapshot 之后)新写的 archival 合进 staging
--     Sleep 跑 5 min 期间 Awake 可能 INSERT 了几条新 archival 到 main
INSERT INTO archival_facts_staging
  SELECT * FROM archival_facts
  WHERE created_at > snapshot_ts
ON CONFLICT (id) DO NOTHING;

-- (c) 合并已有 fact 的并发字段:
--     语义字段保留 staging(Sleep),访问统计取更新值(Awake),
--     软删除是单向状态,任意一边删除都保留
UPDATE archival_facts_staging AS staging
SET use_count = GREATEST(staging.use_count, main.use_count),
    last_used_at = CASE
      WHEN staging.last_used_at IS NULL THEN main.last_used_at
      WHEN main.last_used_at IS NULL THEN staging.last_used_at
      ELSE GREATEST(staging.last_used_at, main.last_used_at)
    END,
    is_deleted = staging.is_deleted OR main.is_deleted
FROM archival_facts AS main
WHERE staging.id = main.id;

-- (d) 三步 RENAME 切换 main ↔ staging(用 tmp 名做中转)
ALTER TABLE archival_facts RENAME TO archival_facts_tmp_swap;
ALTER TABLE archival_facts_staging RENAME TO archival_facts;
ALTER TABLE archival_facts_tmp_swap RENAME TO archival_facts_staging;
-- core_blocks 同样三步

-- (e) TRUNCATE 现在的 staging(里面是旧 main 数据,不需要了)
TRUNCATE archival_facts_staging;
TRUNCATE core_blocks_staging;

-- (f) 把本轮 Sleep 的 pending_ops 写入主审计日志
--     和 swap 在同一个 transaction 里:主表切换成功,日志才成功
INSERT INTO memory_ops_log
  (op_type, actor, target_kind, target_id, before_value, after_value, reason)
VALUES
  (...pending sleep ops...);

COMMIT;
```

→ Awake 下次 SELECT 自动拿到新版数据,**无感切换**。

---

### [graph END]

```
不 aborted → _last_cycle_ts = now()  (记录这次成功 cycle)
▼ 返回 summary:
{
  "status": "ok",
  "plan": ["consolidate", "promote", "core_refresh", "reflect"],
  "consolidate_count": 2,
  "promote_candidate_count": 5,
  "promote_count": 2,
  "demote_count": 0,
  "contradictions_count": 0,
  "core_refresh_checked": true,
  "core_refresh_evidence_mode": "all_active",
  "core_refresh_candidate_count": 5,
  "core_refresh_count": 1,
  "reflection_preview": "User is a Java backend intern..."
}
▼ scheduler: _cycle_running = False  (下次 trigger 又能启动)
▼ logger.info("sleep cycle (trigger=idle) result=...")
```

---

> **staging table**(临时工作表):跟主表 schema 一样的副本。Sleep 在 staging 上改东西,改完一口气切换到 main。Sleep 跑期间 Awake 完全不受影响(它读写 main,看不到 staging)。

> **atomic swap**(原子切换):用 transaction 包住 Core / Archival 两组三步 RENAME,要么两组全部切换并写入 pending logs,要么全部回滚。Awake 不会看到中间改名状态。

> **lock_timeout**:`ALTER TABLE RENAME` 需要短暂拿 `ACCESS EXCLUSIVE LOCK`。Mneme 在 swap transaction 内设置 `lock_timeout=500ms`;如果当时撞上慢查询或长事务,本轮 swap 快速失败并清理 staging,不把在线读写堵在队头。

> **字段级合并**:snapshot 之后,Awake 可能继续对旧 fact 执行 recall / forget。swap 前按字段所有权合并:内容、标签、confidence、stability、salience 和 embedding 保留 Sleep 在 staging 的整理结果;`use_count` / `last_used_at` 保留 Awake 在主表的最新访问统计;`is_deleted` 对两边做 OR,避免 Sleep demote 或 Awake forget 后 fact 在 swap 中复活。合并前的 `SHARE ROW EXCLUSIVE` 锁会阻止新写入插入合并与 RENAME 之间的窗口,但不阻塞普通 SELECT。

> **pending_ops**:Sleep phase 对 staging 的每次修改都会生成一条日志草稿,暂存在 LangGraph state 里。只有 `atomic_swap` 成功时,这些草稿才会在同一个 transaction 内写入主 `memory_ops_log`。如果 swap 失败,主表不变,日志也不写,避免出现"日志说生效但主表没更新"的审计歧义。

> **core refresh checkpoint**:`sleep_core_refresh` 中 `target_id='__checkpoint__'` 的特殊审计记录,表示此前相关变化已被 Refresh 检查。它也是 pending op,所以只有 Core 修改和最终 swap 成功后才能推进游标;全部 `KEEP` 也会记 checkpoint,但没有相关变化时不会重复记录。

> **promote_candidate_count vs promote_count**:`promote_candidate_count` 是本轮 promote 阶段交给模型评估并返回判断的数量,里面可能包含 `SKIP`;`promote_count` 只统计真正 `decision = PROMOTE`、会改写 core 并生成 `sleep_promote` pending op 的数量。看 Sleep 是否真的改了 core,以 `promote_count` 和 `memory_ops_log.sleep_promote` 为准。

> **ALTER TABLE RENAME**:Postgres 支持在 transaction 内改表名。MySQL 也支持,SQLite 不支持。

> **ON CONFLICT (id) DO NOTHING**:Postgres 的 upsert 简化版,id 重复就忽略不报错。用来处理"Awake 期间新增的 archival" 这种 edge case。

---

## 7. 数据库三大表 + 两个 staging

**先看 core_blocks 跟 archival_facts 的关系**(两者**都是 memory**,但形态完全不同——这是 mneme 借鉴 Letta 的两层 memory 设计):

| | core_blocks(核心块) | archival_facts(归档事实) |
|---|---|---|
| **形态** | 结构化大文本块 | 零散小条目 |
| **数量** | 固定 5 个 label | 无限条 |
| **内容长度** | 每个 label 一段几百字 markdown | 一条几句话 |
| **检索方式** | 全量加载(总共几 KB,很小) | 向量检索找最相似 K 个 |
| **写入方** | **只 Sleep agent**(read-only primary) | Awake + Sleep 都能写 |
| **改动频率** | 低(Sleep promote 时才改) | 高(Awake 每次 remember 都写) |
| **生物学类比** | 长期记忆 / 内化的人格 | 短期记忆 / 工作记忆 |
| **角色** | LLM 整合后的 user 画像(综合) | 原始 fact 仓库(零散) |

**关系**:Awake 写 archival(便宜快),Sleep 定期把**高频 + 事实明确 + long_term + 高 salience** 的 archival **promote 进对应的 core_block**(LLM 加工成段落)。

→ **archival = 原始数据;core_block = 提炼后的洞察**。

### 7.1 `core_blocks`(用户画像 — 结构化大颗粒)

5 个固定 label:

- `background` — 你的身份(Java backend 实习生)
- `preferences` — 偏好(4 空格 / Ruff)
- `habits` — 工作习惯(先写测试)
- `skills` — 技术栈 + 熟练度
- `lessons_learned` — 跨项目教训

每个 block 一个 row,value 是 markdown / free text。

**只有 Sleep 写,Awake 只读。**

### 7.2 `archival_facts`(零散事实 — 小颗粒 + 向量)

每条一个 fact(几句话),有:

- `confidence`(1/2/3)
- `stability`(`long_term` / `stage` / `temporary`)
- `salience`(1/2/3)
- `tags` — 标签数组
- `embedding`(1024 维向量)
- `use_count`(被 recall 多少次)
- `is_deleted`(软删除标记)

**Awake 写新的,Sleep 整理(合并 / 升 core / 软删)。**

### 7.3 `memory_ops_log`(审计日志 — append-only)

每次 memory 变更都写一行。

- `op_type`(remember / forget / sleep_consolidate / sleep_promote / sleep_demote / sleep_resolve / sleep_core_refresh / sleep_reflect / policy_violation 等)
- `actor`(awake_agent / sleep_agent)
- `before_value` / `after_value`
- `reason`

只 INSERT,不 UPDATE 也不 DELETE。后期人工 review / 给 Sleep 看历史用。

### 7.4 `memory_write_jobs`(写请求持久化队列)

`remember` / `forget` 不再直接创建内存后台任务,而是先写这张表:

- `operation`: `remember` / `forget`
- `command`:worker 复用 Awake 时要执行的自然语言 command
- `payload`:原始结构化参数,便于排查
- `dedupe_key`:同一 operation + command 的 sha256,防止完全相同请求重复入队
- `status`: `pending` / `running` / `succeeded` / `failed`
- `attempt_count` / `max_attempts`:重试计数
- `available_at`:下一次可执行时间,用于失败退避
- `locked_at`:worker claim 时间,用于恢复卡住的 `running`
- `last_error` / `result`:失败原因或 Awake 返回结果

**和 `memory_ops_log` 的区别**:

| 表 | 语义 |
|---|---|
| `memory_write_jobs` | 待执行/执行中的写入意图。`accepted` 后一定有这一行 |
| `memory_ops_log` | 已经真正改变 memory 后的审计日志 |

也就是说:

```text
memory_write_jobs.succeeded
→ Awake 已经执行完成
→ archival_facts / memory_ops_log 才应该出现对应变化
```

### 7.5 `core_blocks_staging` / `archival_facts_staging`(Sleep 工作表)

Sleep cycle 启动时 `DROP + CREATE` 一份 staging 副本。成功 `atomic_swap` 后,原来的 staging 会变成新的 main,原来的 main 会被改名成新的 staging,然后被 `TRUNCATE` 清空。也就是说:**成功 swap 后 staging 表会保留,但应该是空表**。

`cleanup_staging()` 只在 cycle aborted / 没有 snapshot_ts / 显式清理测试时执行,会把 staging 表真正 `DROP` 掉。当前主路径选择保留空 staging 表,是因为三步 RENAME 本身会自然留下"旧 main 改名后的 staging";下次 snapshot 开始时仍会先 `DROP TABLE IF EXISTS *_staging CASCADE`,所以这些空表不会影响下一轮。

---

## 8. 三道保险(读写权限分离)

> **read-only primary**(术语,Letta paper 提的):Primary agent(我们这里 = Awake)对核心 memory 只读不写。mneme 严格照搬。

| 防线 | 在哪 | 干啥 |
|---|---|---|
| 第 1 道(prompt) | `awake/agent.py:SYSTEM_PROMPT` | 教 LLM:"你 NEVER 写 core_blocks" |
| 第 2 道(应用层) | `memory/store.py:write_core_block` | `if actor != "sleep_agent": raise PermissionError + log policy_violation` |
| 第 3 道(DB 自检) | `core_blocks.last_writer` 字段 | 默认 `sleep_agent`,Sleep 写时 SET = 'sleep_agent';未来加 trigger 校验 |

**为什么 3 道**:LLM 可能 prompt 写得不到位偶尔越界,应用层是兜底;应用层代码可能 bug,DB 字段是最后防线。**Defense in depth(纵深防御)**——任何单层失效都不破。

---

## 9. 术语速查词典(本文出现过的全在这)

| 术语 | 是什么 / 干啥 |
|---|---|
| **MCP**(Model Context Protocol) | Anthropic 协议,AI 客户端调外部 tool 的标准接口 |
| **MCP host** | 装了 MCP 客户端的程序(Claude Code / Cursor / Cline) |
| **MCP server** | 实现 MCP 协议、暴露 tool 给 host 用(mneme 就是) |
| **streamable-http transport** | MCP 的一种通信方式,HTTP + SSE 流式响应 |
| **agent** | LLM 在循环里用 tool 自主决策(对比 workflow:固定步骤) |
| **workflow** | 代码写死步骤,LLM 是其中某一步,无自主决策 |
| **worker** | 后台消费者。Mneme 的 memory worker 从 `memory_write_jobs` 取 pending job,复用 Awake 执行真正写入 |
| **durable queue** | 持久化队列。任务先落 PostgreSQL 表再异步执行,进程崩溃不会丢掉已 accepted 的写入意图 |
| **ReAct** | Reason → Act → Observe 循环,agent 最基础的工作模式 |
| **LangGraph** | Python 库,用图(节点+边)组织 agent 多步逻辑 |
| **StateGraph** | LangGraph 提供的状态机模式(对比 prebuilt ReAct) |
| **system prompt** | LLM 启动时塞给它的"角色设定 + 行为规则" |
| **tool / @tool** | LLM 能调用的函数,LangChain 用 decorator 注册 |
| **embedding**(嵌入向量) | 文本 → 几百几千维向量,语义相近向量也相近 |
| **vector(1024)** | pgvector 的列类型,存 1024 个 float |
| **cosine distance**(余弦距离) | 向量"角度差",0=一样 1=无关 2=反向 |
| **HNSW** | 向量索引算法,毫秒级找最近邻 |
| **pgvector** | Postgres 扩展,加 vector 类型 + 距离运算 |
| **PostgreSQL** | 开源关系型数据库 |
| **extension**(PG 扩展) | Postgres 的插件机制(pgvector / postgis 等) |
| **transaction**(事务) | 一组 SQL 原子执行,全成功或全回滚 |
| **staging table** | 副本表,做改动用,完成后 swap 替换主表 |
| **atomic swap**(原子切换) | transaction 内的表名切换 |
| **ALTER TABLE RENAME** | PG 支持在 tx 内改表名 |
| **sleep-time compute** | Letta paper 术语:agent idle 时用 compute 整理 memory |
| **read-only primary** | Letta paper 术语:主 agent 不能写主 memory,只 Sleep 能写 |
| **APScheduler** | Python 定时任务库,支持 cron / interval / date 触发 |
| **AsyncIOScheduler** | APScheduler 跑在 asyncio event loop 上的版本 |
| **idle detection** | 检测"多久没活动"的逻辑 |
| **single-flight** | 同一时刻只允许一个 cycle 跑,跨触发也防并发 |
| **soft delete**(软删除) | 不真删 row,只标记 `is_deleted=true`,可恢复 |
| **append-only** | 表只 INSERT 不 UPDATE/DELETE(audit log) |
| **defense in depth**(纵深防御) | 多层保险,任意单层失效都不破 |
| **Starlette** | Python ASGI web 框架(FastAPI 基于它) |
| **ASGI** | Python 异步 web 协议标准 |
| **lifespan** | Starlette 的"启动 + 关闭"hook |
| **uvicorn** | ASGI server(跑 ASGI app 的进程) |
| **AsyncSession** | SQLAlchemy 异步数据库 session |
| **ChatOpenAI** | LangChain 包装的 OpenAI-compatible LLM 客户端 |
| **DeepSeek** | 中国 LLM,提供 OpenAI 兼容 API,便宜 |
| **text-embedding-v3**(阿里通义) | dashscope OpenAI-compatible 端口,1024 维,国内顺畅 |
| **idempotent**(幂等) | 跑多次结果一样(`setup.sh` 是幂等的) |
| **pydantic-settings** | Python 库,从 `.env` 读配置成类型化对象 |
| **session**(对话) | Claude Code 一次对话窗口,关掉就消失 |
| **CLAUDE.md** | Claude Code 启动时自动读的 project 根目录 markdown |
| **auto memory**(Claude Code 的) | Claude Code 自己写的 markdown,per-project |

---

## 10. 一句话总结流程

**Awake**:你跟 Claude Code 聊天 → LLM 觉得该记 / 该查 → MCP 调 mneme → Awake agent 跑 ReAct → 读/写 archival_facts → 返回。

**Sleep**:你不在的时候 → APScheduler 触发 → Sleep agent 跑 9 节点 StateGraph → 用 LLM 决定 plan,合并、升级、淘汰、解决矛盾、刷新 core、写 reflection → atomic swap → 整理完。

**核心**:Awake 写一堆零散 fact 到 archival,Sleep 用 LLM 把零散的提炼成结构化的 core blocks——这就是 **sleep-time consolidation**(睡眠时整合)。

---

## 相关文档

- `docs/PLAN.md` — 总方案 17 节,设计动机 + 决策
- `docs/DECISIONS.md` — Q1-Q14 全部拍板决策
- `docs/CODE_REVIEW.md` — 15 个 known risk,代码跑前必读
- `docs/QUICKSTART.md` — 回家 5 步
- `docs/research-notes/letta-sleep-time-paper-notes.md` — Letta paper 笔记(arxiv 2504.13171)
