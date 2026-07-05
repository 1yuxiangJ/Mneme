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

干啥:在 idle 时整理 memory(合并重复 / 升级常用 / 删除过期 / 解决矛盾 / 写 reflection 一段"about user")。

> **APScheduler**:Python 定时任务库。能用 cron 表达式(`0 3 * * *` = 每天 03:00)或 interval(每 60 秒一次)触发函数。
>
> **idle**(空闲):没人在用。我们用 "上次 Awake 被调用时间 + 30 min" 判断。

### 3.4 4 个 MCP tool 详解(暴露给 Claude Code 的)

这 4 个 tool 是 mneme 跟 Claude Code 唯一的接口。`mcp_server.py` 里注册,签名固定。

#### `remember(content, tags=None, confidence=2)`

**何时被调**:Claude Code 的 LLM 在对话中**自己判断**"用户透露了关于他这个人的事实",主动调用。**不是用户喊"记一下"**——是 LLM 自主决策(LLM-driven memory writes,Letta paper 核心范式)。

例 1:你说"我决定以后所有项目都用 Ruff" → LLM 内部判断这是 cross-project 偏好 → 调 `remember("user prefers Ruff", ["preference", "tooling"], 3)`

例 2:你说"足球、游戏、刷 B 站/抖音基本是我长期的放松方式" → LLM 内部判断这是稳定生活偏好 → 调 `remember("user relaxes through football, games, Bilibili, and Douyin", ["lifestyle", "hobby", "entertainment"], 3)`

**应该记的范围**:关于用户这个人的长期稳定事实,不只限工作学习。包括身份、目标、技能、沟通偏好、工作/学习习惯、长期兴趣爱好、娱乐偏好、生活习惯、放松方式、产品/审美偏好、稳定喜欢/不喜欢。

**不应该记的范围**:临时状态、当天计划、一次性事件、短期情绪、项目内部事实。比如"今天有点累"不记;"最近游戏机不在身边"默认不记,除非用户确认这是长期模式。

**mneme 内部**:MCP tool 先快速返回 `accepted`;后台 Awake agent ReAct → 先 `search_archival` 去重 → 没重复就 `insert_archival_fact` → 写 `memory_ops_log`

**返回**:`{"status": "accepted", "mode": "async", "operation": "remember"}`

**为什么异步**:`remember` 是写类操作,Claude Code 当前回答通常不依赖 fact_id。同步等待会把 LLM ReAct + embedding + DB 写入的 2-5 秒延迟叠到用户体验上。Mneme 选择写异步、读同步:`remember` / `forget` 后台处理,`recall` / `list_memory` 同步返回可用结果。

**参数**:
- `content`:要记的事实(自然语言)
- `tags`:标签数组(给后续 demote/promote 筛选用)
- `confidence`:给 Sleep 决定 promote/demote 的稳定性信号,不是 LLM 自报概率。

`confidence` 三档语义:

| 值 | 语义 | 例子 |
|---|---|---|
| 3 | stable long-term fact:用户明确表达的长期稳定事实 | "用户喜欢足球";"用户偏好直接具体的中文解释" |
| 2 | stage-specific / recent but useful:阶段性、最近状态、上下文相关,可能变化 | "用户最近主要玩 CS2";"用户当前 PS5/NS 不在身边" |
| 1 | tentative / inferred:弱确认、推断、试探性事实 | "用户可能对某类游戏感兴趣" |

如果一句话里混合长期事实和临时细节,应该拆开保存成多条不同 confidence 的记忆,或者跳过临时细节。不能把整句话统一打成 `confidence=3`。

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

**mneme 内部**:MCP tool 快速返回 `accepted`;后台 Awake agent ReAct → `forget_archival` → 软删除(`is_deleted=true`)+ ops log

**返回**:`{"status": "accepted", "mode": "async", "operation": "forget"}`

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

- 高 confidence + 短文本 → LLM 可能跳过 search 直接 insert
- 低 confidence + 长文本 → 先 search 看有没有近似
- 检测到 dup → LLM 决定 skip / merge / 还是 insert

简单 case(`forget`)看起来是 1:1 多此一举,但**统一架构**有好处:未来想加复杂逻辑只改 prompt,不动代码。`list_memory` 是例外:它是新 session 的启动读路径,必须尽量稳定、低延迟、低成本,所以直接查 DB。

**4 个 MCP tool ↔ Awake 5 个内部 @tool 对应表**:

| MCP tool(Layer 1) | Awake 内部 @tool(Layer 2) | 关系 |
|---|---|---|
| `remember` | `search_archival` + `insert_archival_fact` | 1:多(LLM 决定怎么组合);MCP 层异步返回 |
| `recall` | `load_core` + `search_archival` | 1:多 |
| `list_memory` | 不走 Awake;MCP 层直读 DB | direct DB fast path |
| `forget` | `forget_archival` | 1:1(简单 case);MCP 层异步返回 |

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
                       tags=["preference"], confidence=3)
                                │
                                │ (mcp_server.py 收到 → schedule background task)
                                ▼
                       mark_awake_activity()  ← 重置 idle 计时器
                                │
                                ├── 立刻返回 {status: "accepted", mode: "async"}
                                │
                                ▼
                       后台任务调用 run_awake(command)
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
              ◄─── 后台任务完成;如果失败写服务日志
```

**异步写入的代价**:Claude Code 收到 `accepted` 时,事实不一定已经落库。刚 `remember` 后立刻 `recall` 可能暂时查不到,这是最终一致性取舍。读类工具 `recall` / `list_memory` 仍然同步,因为它们的结果会直接影响当前回答。

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
  "phases": ["consolidate", "promote", "reflect"],
  "reason": "8 new archival since last cycle (dedup); 3 high-freq for promote; reflect always at end"
}
```

→ `state["plan"] = ["consolidate", "promote", "reflect"]`

后续每个 phase node 入口都 check `if "phase" not in state["plan"]: pass through`。

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

**为啥**:archival 里"被反复用 + confidence 高"的 fact,该提升到结构化的 core block,成为用户画像的固定一部分。**Sleep 是 core_blocks 的 sole writer**(Letta read-only primary)。

**做啥**:
1. SQL 找 `use_count >= 5 AND confidence = 3` 的 archival
2. 把候选 + 当前 core_blocks 喂 LLM(LLM 要看 core 当前内容才能写新值)
3. LLM 决定哪些 PROMOTE / SKIP,PROMOTE 到哪个 core block,新 block 整段 value 是什么
4. 应用到 `core_blocks_staging`

**例子**:
- 候选 archival:
  ```
  [id=88,  use_count=7,  conf=3, "user prefers 4-space indentation"]
  [id=199, use_count=12, conf=3, "user writes tests first"]
  [id=158, use_count=5,  conf=3, "user dislikes nested lambdas"]
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
     "reason": "Python-specific syntax preference, not generalizable"}
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

**为啥**:archival 是零散事实仓库,只增不清会越来越吵。Sleep 需要把"长期没被用到 + 低 confidence"的事实软删,降低 recall 噪音和后续 Sleep 的处理成本。

**注意**:`demote` 不是删 core block。core block 是高层用户画像,只有 `promote` / `resolve` 会改 core;`demote` 当前只处理 `archival_facts_staging` 里的低价值 fact。

**做啥**:
1. SQL 找 stale candidates:长期没被 recall 用过、confidence 低、还没被软删的 archival
2. 把候选喂 LLM `DEMOTE_PROMPT`
3. LLM 对每条判断 `FORGET` / `KEEP`
4. 只对 `FORGET` 的 fact 在 staging 表里 `is_deleted = TRUE`
5. 生成 `pending_ops(op_type='sleep_demote')`

**例子**:
- 候选 archival:
  ```
  [id=31, confidence=1, last_used_at=120 days ago, "user might try Flask someday"]
  [id=44, confidence=2, last_used_at=110 days ago, "user once asked about Kotlin syntax"]
  [id=88, confidence=3, last_used_at=140 days ago, "user prefers 4-space indentation"]
  ```
- LLM 决定:
  ```json
  {
    "actions": [
      {"fact_id": 31, "decision": "FORGET", "reason": "low-confidence tentative interest, never reused"},
      {"fact_id": 44, "decision": "KEEP", "reason": "could reflect Java ecosystem interest"},
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

archival 层不强求全局一致,因为它保留的是"用户曾经表达过什么";core 层必须自洽,因为它代表"系统当前相信的用户画像"。

后续如果要专门处理 archival 冲突,可以新增 `reconcile_archival` phase,做 supersede 标记、降低旧 fact confidence、补时间范围,而不是简单删除其中一条。

---

### Node 7: reflect ← 输出一段 "about user" 摘要

**为啥**:产出自然语言"about user"段落,供人 review(看 Sleep 整理得对不对),也给后续 cycle 提供 context。

**做啥**:
1. 拿(已被 promote 改过的)core_blocks + 高 conf archival 5 条
2. 喂 LLM `REFLECT_PROMPT`,要求 2-4 句话
3. 生成 `pending_ops(op_type='sleep_reflect')`

**LLM 输出例**:
> "User is a Java backend intern at Thunderbit, job-hunting for Java backend and AI agent roles. Prefers Ruff and 4-space indent. Writes tests before implementation. Recently learned to avoid nested asyncio.gather in for-loops."

---

### Node 8: swap ← atomic 切换 staging → main

**为啥**:把已被 Sleep 改过的 staging 切换成新 main。**原子**切换避免 Awake 看到"半成品"状态。

**做啥**(全部在单 transaction 内):

```sql
BEGIN TRANSACTION;

-- swap 会拿 ACCESS EXCLUSIVE LOCK;拿不到锁就快速失败,避免队头阻塞在线请求
SELECT set_config('lock_timeout', '500ms', true);

-- (a) 把 Awake 期间(snapshot 之后)新写的 archival 合进 staging
--     Sleep 跑 5 min 期间 Awake 可能 INSERT 了几条新 archival 到 main
INSERT INTO archival_facts_staging
  SELECT * FROM archival_facts
  WHERE created_at > snapshot_ts
ON CONFLICT (id) DO NOTHING;

-- (b) 三步 RENAME 切换 main ↔ staging(用 tmp 名做中转)
ALTER TABLE archival_facts RENAME TO archival_facts_tmp_swap;
ALTER TABLE archival_facts_staging RENAME TO archival_facts;
ALTER TABLE archival_facts_tmp_swap RENAME TO archival_facts_staging;
-- core_blocks 同样三步

-- (c) TRUNCATE 现在的 staging(里面是旧 main 数据,不需要了)
TRUNCATE archival_facts_staging;
TRUNCATE core_blocks_staging;

-- (d) 把本轮 Sleep 的 pending_ops 写入主审计日志
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
  "plan": ["consolidate", "promote", "reflect"],
  "consolidate_count": 2,
  "promote_count": 2,
  "demote_count": 0,
  "contradictions_count": 0,
  "reflection_preview": "User is a Java backend intern..."
}
▼ scheduler: _cycle_running = False  (下次 trigger 又能启动)
▼ logger.info("sleep cycle (trigger=idle) result=...")
```

---

> **staging table**(临时工作表):跟主表 schema 一样的副本。Sleep 在 staging 上改东西,改完一口气切换到 main。Sleep 跑期间 Awake 完全不受影响(它读写 main,看不到 staging)。

> **atomic swap**(原子切换):用 transaction 包住 RENAME,要么三个表名全切完,要么一个都不切。中间不会出现"主表有名但里面是 staging 数据"这种半成品状态。

> **lock_timeout**:`ALTER TABLE RENAME` 需要短暂拿 `ACCESS EXCLUSIVE LOCK`。Mneme 在 swap transaction 内设置 `lock_timeout=500ms`;如果当时撞上慢查询或长事务,本轮 swap 快速失败并清理 staging,不把在线读写堵在队头。

> **pending_ops**:Sleep phase 对 staging 的每次修改都会生成一条日志草稿,暂存在 LangGraph state 里。只有 `atomic_swap` 成功时,这些草稿才会在同一个 transaction 内写入主 `memory_ops_log`。如果 swap 失败,主表不变,日志也不写,避免出现"日志说生效但主表没更新"的审计歧义。

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

**关系**:Awake 写 archival(便宜快),Sleep 定期把**高频 + 高 confidence** 的 archival **promote 进对应的 core_block**(LLM 加工成段落)。

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
- `tags` — 标签数组
- `embedding`(1024 维向量)
- `use_count`(被 recall 多少次)
- `is_deleted`(软删除标记)

**Awake 写新的,Sleep 整理(合并 / 升 core / 软删)。**

### 7.3 `memory_ops_log`(审计日志 — append-only)

每次 memory 变更都写一行。

- `op_type`(remember / forget / sleep_consolidate / sleep_promote / sleep_demote / sleep_resolve / sleep_reflect / policy_violation 等)
- `actor`(awake_agent / sleep_agent)
- `before_value` / `after_value`
- `reason`

只 INSERT,不 UPDATE 也不 DELETE。后期人工 review / 给 Sleep 看历史用。

### 7.4 `core_blocks_staging` / `archival_facts_staging`(Sleep 工作表)

Sleep cycle 启动时建,跑完 swap,cleanup 时删。**main 跟 staging 的角色每个 cycle 都互换一次**(因为 swap 是三步 RENAME)。

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

**Sleep**:你不在的时候 → APScheduler 触发 → Sleep agent 跑 8 节点 StateGraph → 用 LLM 决定 plan,合并、升级、淘汰、解决矛盾、写 reflection → atomic swap → 整理完。

**核心**:Awake 写一堆零散 fact 到 archival,Sleep 用 LLM 把零散的提炼成结构化的 core blocks——这就是 **sleep-time consolidation**(睡眠时整合)。

---

## 相关文档

- `docs/PLAN.md` — 总方案 17 节,设计动机 + 决策
- `docs/DECISIONS.md` — Q1-Q14 全部拍板决策
- `docs/CODE_REVIEW.md` — 15 个 known risk,代码跑前必读
- `docs/QUICKSTART.md` — 回家 5 步
- `docs/research-notes/letta-sleep-time-paper-notes.md` — Letta paper 笔记(arxiv 2504.13171)
