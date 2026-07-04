# Mneme 项目精讲笔记

> 用户(项目作者)系统学习自己项目的精讲笔记,按章节累积。每讲完一章都追加进来。
>
> **文档进度**:§0 - §8 正文全部写完。每章末尾有课后思考题待回答。
>
> **学习进度**:2026-07-01 已学完 §5,开始学习 §6。
>
> **如何阅读**:章节顺序累进,Q&A 嵌在每个对应章节末尾(保留学习轨迹)。和 `PLAN.md` / `ARCHITECTURE.md` 的关系——那俩是产物文档,**这份是讲解 + 问答**,可读性优先。

---

# §0 · 导航 + 怎么用

| 章 | 内容 | 状态 |
|---|---|---|
| §1 | 项目是什么(30 秒电梯版 + 边界) | 完成 |
| §2 | 技术选型(每颗螺丝为啥是这颗) | 完成 |
| §3 | 架构 4 层(MCP / Agent / Store / Scheduler) | 完成 |
| §4 | 数据模型(core_blocks / archival_facts / ops_log / staging) | 完成 |
| §5 | 两条端到端流程(remember 链路 + sleep cycle 链路) | 完成 |
| §6 | 四个最难的实现细节 | 完成 |
| §7 | 已知 trade-off | 完成 |
| §8 | 面试 18 连问 | 完成 |

**§1-§4** 是把项目讲清楚的最小必要集;**§5-§6** 是讲透的高难度集;**§7** 是防忽悠层;**§8** 是话术打包。

---

# §1 · 项目是什么

## 1.1 30 秒电梯版

> **Mneme = 给 Claude Code 装的"跨 project 长期记忆服务"**,通过 MCP 协议接入。
>
> 严格按 Letta sleep-time compute paper(arxiv 2504.13171)实现 **Awake / Sleep 双 agent + read-only primary** 架构。Awake 实时响应 `remember/recall`(只能读 core / 写 archival),Sleep 在 idle 时跑 consolidation / promotion / reflection(是 **core_blocks 的唯一 writer**)。并发用 staging snapshot + atomic swap 解决。

## 1.2 边界

| 谁 | 范围 |
|---|---|
| **Claude Code 自己** | 当前 session context、`CLAUDE.md`、per-project auto memory |
| **Mneme(我们)** | **跨 project 的"关于用户这个人"的 fact**(偏好 / 习惯 / 教训 / 画像) |

举例:

| 场景 | 谁记? |
|---|---|
| "我喜欢 4 空格" | Mneme(跨项目偏好) |
| "thunderbit-server 用 Spring Boot 3" | Claude Code 的 CLAUDE.md(项目内) |
| "asyncio.gather 不要嵌 for loop" | Mneme(跨项目教训) |
| "这个 bug 改 UserService.java:42" | Claude Code 的 session context(当下) |

## 1.3 故意不做的事

| 不是 | 为啥 |
|---|---|
| chatbot | 不跟人聊天,只暴露 4 个 MCP tool |
| RAG 知识库 | 不索引文档,只装"关于用户这个人"的 fact |
| mem0 / cognee 的 fork | 不 fork,参考 Letta paper 自研 |
| Claude Code 自带 memory 的替代品 | 故意收窄边界,跟 CLAUDE.md 互补 |
| multi-tenant SaaS | MVP 单用户写死 `user_id = "userjyx"` |

## 1.4 为什么这个边界这么重要

这是项目**存在意义的根**。

不收窄边界 → 退化成"另一个 RAG 项目",简历跟"智能 xx 知识库"撞型。

收窄到"跨 project 用户画像" → 落在 Claude Code **故意留出来**的空白(CLAUDE.md 和 auto-memory 都 per-project,跨 project 是真空):

1. **场景具体** → judgment 规则可以收敛(5 个 core blocks 就够)
2. **目标用户同质**(都是程序员)→ 不用考虑通用产品的隐私 / 合规噩梦
3. **跟 Anthropic 不冲突** → MCP 协议本身就是 Anthropic 留给生态填的位置

面试问"为啥不像 ChatGPT Memory 那样大而全",答:**不收窄边界,就没有项目**。

## §1 小结(背一段)

> "Mneme 通过 MCP 给 Claude Code 加一层跨 project 用户画像长期记忆,边界严格限定在'关于用户这个人'的 fact,跟 Claude Code 自带的 CLAUDE.md 和 per-project auto-memory 互补。"

---

# §2 · 技术选型

> 重点不是"用了什么",而是"为什么是这个不是那个"——面试官真正想听的是**取舍**。

---

## §2.1 · 语言 —— Python

### 决策

Python 3.11+。不用 Java(虽然作者是 Java 实习)。

### 为什么

| 选项 | 取舍 |
|---|---|
| Python | AI agent 生态主场。LangGraph、MCP SDK、pgvector client、LangChain 全部 Python 一线维护 |
| Java | LangChain4j 落后官方 Python 版 2-3 个版本,MCP 官方 Java SDK 还在 alpha |
| Go | LangChain-Go 几乎死活,MCP Go SDK 维护差 |
| TypeScript | MCP 官方有 TS SDK(成熟),但 LangGraph TS 版功能差 Python 版一大截 |

核心判断:agent 框架的**最新能力都首发在 Python**。

### 跟 Java 实习冲突怎么答(面试稿)

> "我求职双线投——Java backend 主线,这个项目是差异化补充。Java 我有 Thunderbit 实习背书,常规 backend 题不需要再用项目证明。这个项目要展示 **AI agent + 架构设计 + 系统设计** 能力,Python 是行业主场,LangGraph / MCP / Letta paper 引用实现都在 Python 生态。用 Java 反而会被追'为啥不用主流栈',那个故事更难讲。
>
> 另外这个项目里 90% 的复杂度不在语言上——是在 **read-only primary 怎么落地**、**staging swap 怎么不阻塞**、**Sleep cycle 8 阶段怎么协调**。这些设计原则跟语言无关,Java 重写也是同一套架构。"

### 反方观点防御

| 反驳 | 答 |
|---|---|
| "Python 性能差" | 场景是 idle-time consolidation,瓶颈在 LLM API(秒级)不在 Python(毫秒级) |
| "Python 类型系统弱" | `from __future__ import annotations` + pydantic + SQLAlchemy 2.0 typed `Mapped[]`,IDE 提示满分 |
| "Python 并发模型烂" | `async/await` + asyncpg + APScheduler AsyncIOScheduler,IO 密集场景的 async 很成熟 |

---

## §2.2 · Agent 框架 —— LangGraph

### 决策

LangGraph。两种 API 都用:
- **Awake** 用 `create_react_agent`(prebuilt ReAct agent)
- **Sleep** 用 `StateGraph`(手拼节点/边的状态图)

### 先补:什么是 ReAct

ReAct = Reason + Act(2022 年 Google 论文)。LLM 反复跑:

```
[Reason] LLM 想下一步干啥
   ↓
[Act] 调一个 tool
   ↓
[Observe] 工具返回,塞回 LLM context
   ↓
回到 Reason,直到 LLM 说"搞定"
```

示例(`remember` 链路):

```
用户:remember "我喜欢 4 空格"

Reason 1:  LLM 想:先查重复
Act 1:     search_archival(query="我喜欢 4 空格")
Observe 1: [] (没找到)

Reason 2:  LLM 想:没重复,可以插入
Act 2:     insert_archival_fact(content="...", tags=["preference"])
Observe 2: {"status": "ok", "fact_id": 123}

Reason 3:  LLM 想:任务完成
Final:     "已记住: fact_id=123, content='...'"
```

没有 ReAct loop → `remember` 退化成"无脑插数据库" = CRUD 包装 = 项目废。

### 为什么 LangGraph 而不是别的

| 选项 | 取舍 |
|---|---|
| LangGraph | LangChain 官方出品,有 ReAct 模板也有图 DSL |
| 手写 ReAct | 校招生说"自研" 可信度低 + streaming/error/max-iter 样板代码海量 |
| CrewAI | 多 agent 协同框架,我们两个 agent 不需要;封装太厚 |
| AutoGen | 类 CrewAI,聊天式 multi-agent,跟我们严格分工的模型不匹配 |
| Letta SDK 直接调 | 太重 + "调包侠";借鉴 paper 思路自实现是更好叙事 |
| OpenAI function calling 裸用 | 缺 loop / state / error,等于手撸 |

### 两种 LangGraph API 各用在哪

**A. `create_react_agent` —— Awake(`awake/agent.py:55-61`)**

```python
from langgraph.prebuilt import create_react_agent
_agent = create_react_agent(llm, AWAKE_TOOLS, prompt=SYSTEM_PROMPT)
```

为啥 Awake 用这个:Awake 是**自由探索型**——LLM 自己决定调哪个 tool、调几次、什么时候结束。

**B. `StateGraph` —— Sleep(`sleep/agent.py:271-291`)**

```python
g = StateGraph(SleepState)
g.add_node("snapshot", node_snapshot)
g.add_node("plan", node_plan)
...
g.add_edge(START, "snapshot")
g.add_edge("snapshot", "plan")
...
```

为啥 Sleep 用这个:**固定 pipeline**——8 阶段顺序写死,每个节点内 LLM 决策,但节点之间流向硬编码(不能让 LLM 跳过 snapshot 直接 swap)。

### 取舍口诀

> - **agent 该自由探索?** → `create_react_agent`(Awake)
> - **流程固定 + LLM 只在节点内决策?** → `StateGraph`(Sleep)

### §2.2 · Q&A

#### Q1:什么是 "read-only primary" 里的 "primary"?

"primary" 是 Letta paper 从 DB replication 术语借来的,但**语义反过来**:

| | DB 世界 | Letta 世界 |
|---|---|---|
| 谁能写? | primary 能写,replica 只读 | **primary 不能写 core,sleep 才能写 core** |
| 数据流向 | primary → replica | **sleep → primary 看到的 core** |

具体到项目:**Awake(主 agent)对 core_blocks 只读**;**Sleep(后台)是 core_blocks 唯一 writer**。

为啥这么反直觉:Awake 是实时的、可能错的;让它只能写"小水池"(archival),想进"大水池"(core)必须等 Sleep 慢慢审。**两道闸门**——保证 user 画像不会被一时冲动污染。

面试稿:
> "primary 指主 agent(Awake),read-only 是说它对 core_blocks 只读。这是 Letta paper 的访问控制——让实时 agent 不能动核心画像,只有 Sleep 在 idle 时审慎评估后才能 promote 进 core,避免 Awake 一时冲动写错。"

#### Q2:LangChain4j 对应 Python 啥?

**LangChain4j ↔ Python LangChain**(不是 LangGraph)。

```
LangGraph                  ← agent 编排层(StateGraph、conditional edges、checkpoint)
   ↑ 依赖
LangChain (core)           ← 基础抽象层(LLM wrapper、Tool、Chain、Memory)
   ↑ 依赖
LLM API
```

- LangChain:基础 LLM 接口 + 工具,**LangChain4j 对标这里**
- LangGraph:LangChain 团队后出的图编排,**LangChain4j 没等价品**

我们项目两个都用:`langgraph` 做编排,`langchain-openai` 做 LLM 客户端。

如果硬 Java 重写:LangChain4j 可以做基础层,但 Sleep 的 `StateGraph` 8 节点要手撸状态机(switch / sealed class),代码量翻倍。这是 Python 在这项目"自然选择"的硬性理由。

#### Q3:StateGraph 是怎么运作的?node / edge / state 是啥?

**一句话**:**node 是函数,edge 是"跑完这个跑哪个"的指针,state 是从头传到尾的共享背包**。

**node 是函数**(看 `sleep/agent.py:96`):
```python
async def node_snapshot(state: SleepState) -> SleepState:
    if not _budget_ok(state):
        return {**state, "aborted": True, ...}
    ...
    return {**state, "snapshot_ts": ts}
```

约定:入参 `state`,返回 `state`。LangGraph 不关心你内部干啥。

**state 是 TypedDict**:
```python
class SleepState(TypedDict, total=False):
    snapshot_ts: datetime
    plan: list[str]
    consolidate_actions: list
    aborted: bool
    ...
```

把它想象成背包,每个 node 往里塞字段:

```
START → snapshot(加 snapshot_ts) → plan(加 plan) → consolidate(加 consolidate_actions) → ... → END
```

为啥 `return {**state, "new_field": value}` 不是 `state["new_field"] = value`——immutable 风格,方便后续加 checkpoint。

**edge 是顺序**:
```python
g.add_edge(START, "snapshot")
g.add_edge("snapshot", "plan")
```

等价于:
```python
state = await node_snapshot(state)
state = await node_plan(state)
...
```

**那为啥要 LangGraph,直接 await 不行?**
1. **未来加 conditional_edges**(LLM 决定走哪条路),手撸要写一堆 if/else
2. **未来加 checkpoint**(state 每步存盘),手撸要写持久化基础设施
3. **简历叙事**:面试官知道 LangGraph,不用解释

MVP 我们暂时没用 conditional / checkpoint,但结构留好。

#### Q4:Sleep 的 StateGraph 编排是不是就是 workflow?只有 Awake 是真 agent?

**对。Sleep 严格说是 agentic workflow,不是 pure agent。只有 Awake 是 pure ReAct agent。**

Anthropic *Building Effective Agents*(2024-12)分三层:

| 层 | 控制流谁决定 | 例子 |
|---|---|---|
| Workflow | 全部人写死(代码 if/else / DAG) | 翻译 pipeline |
| **Agentic Workflow** | **流程框架人写死,节点内 LLM 决策** | 我们的 **Sleep** |
| **Agent** | **流程也是 LLM 决策**(动态选下一步) | 我们的 **Awake** |

Sleep 每个 node 都调 LLM 做实质决策(plan / consolidate / promote / demote / resolve / reflect),所以**不是哑工作流**。但**节点之间流向写死**——所以也不是 pure agent。**两个特征加起来 = agentic workflow**。

**这不是退化,是正确选择**:
1. Sleep 8 阶段有严格状态依赖(snapshot 必须先、swap 必须后),让 LLM 自由调度有数据损坏风险
2. Letta 真版也是这么做的
3. Anthropic 论文明确建议:可预测性 > 灵活性的场景用 workflow

面试如果被追问:

> "Sleep 严格说是 agentic workflow——节点流向写死,每个节点 LLM 做实质决策(plan / consolidate / promote / demote / resolve / reflect 都是 LLM 输出 JSON action,代码 apply)。这是主动选择不是技术不足:Sleep 8 阶段有严格状态依赖,让 LLM 自由调度有数据损坏风险。Letta paper 的 sleep-time consolidation 也是结构化 pipeline。Awake 是 pure ReAct agent——MCP 请求进来后 LLM 自由决定调哪些 tool / 几次 / 什么时候结束。两种模式各用在对的地方:Awake 需要 flexibility,Sleep 需要 predictability。"

简历措辞:`"Awake is a pure ReAct agent, Sleep is an agentic workflow orchestrating idle-time memory consolidation."`

---

## §2.3 · 数据库 —— PostgreSQL + pgvector

### 决策

PostgreSQL 16+,加 pgvector extension。关系数据 + 向量装在**同一个 DB**。

### 不分两个库

```
传统:                       我们:
MySQL  ←→  Milvus           PostgreSQL
user/fact   embeddings      archival_facts:
                              id, content, ..., embedding vector(1024)
```

核心好处:**事务跨数据库的恶心问题彻底没了**。

### 为啥 PG + pgvector

| 选项 | 取舍 |
|---|---|
| PG + pgvector | 一个 DB 装关系 + 向量,HNSW 工业级 |
| MySQL + Milvus | 双库,数据同步麻烦,事务不能跨 |
| Pinecone(SaaS) | 云服务,本地 demo 不能用 |
| Qdrant / Weaviate | 独立服务,多组件多脆弱性 |
| SQLite + sqlite-vec | 嵌入式好,但缺事务并发、缺成熟 HNSW |

**关键判断**:MVP 单 DB 绝对正解,生产到亿级 vector 再考虑专用向量库。我们项目永远到不了那个量级。

### 代码里怎么用

**列定义**(`db/models.py:62`):
```python
from pgvector.sqlalchemy import Vector

class ArchivalFact(Base):
    ...
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024))
```

**相似搜索**(`memory/store.py:104-133`):
```python
stmt = (
    select(
        ArchivalFact,
        ArchivalFact.embedding.cosine_distance(vec).label("distance"),
    )
    .where(ArchivalFact.is_deleted.is_(False))
    .order_by("distance")
    .limit(limit)
)
```

转 SQL:
```sql
SELECT ..., embedding <=> '[0.1, -0.3, ...]'::vector AS distance
FROM archival_facts
ORDER BY distance LIMIT 5;
```

`<=>` 是 pgvector 的 **cosine distance operator**,C 实现 SIMD 加速。

**HNSW 索引**:
```sql
CREATE INDEX ON archival_facts USING hnsw (embedding vector_cosine_ops);
```

没索引 1 万条 ~50ms,有 HNSW ~2ms。我们项目 1000 条规模其实无所谓,但面试要懂。

### §2.3 · Q&A

#### Q1:fact 和 core 都有 embedding 吗?

**只有 archival_facts 有 embedding,core_blocks 没有**。

| | core_blocks | archival_facts |
|---|---|---|
| 数量 | 永远 5 条 | 千-万条 |
| 怎么用 | 每次全量加载 | 按需检索 |
| 需要 embedding? | 不需要(5 条全读塞 context) | 需要(量大要语义搜) |

对应 Letta 的 "core vs archival" 抽象:
- core memory = 桌面便签纸(5 张,抬头一眼)
- archival memory = 仓库纸箱(几千件,要索引)

#### Q2:HNSW 和 IVF 是什么?

两个 **ANN**(Approximate Nearest Neighbor)算法。

**HNSW(我们用的)**:**分层图**——像地铁线路图,顶层快线少站,底层慢线全站。搜索时先在顶层跳到大致方向,逐层下降细化。**O(log N)**。

**IVF**:**簇 + 倒排**——像电话簿按区号分。先把所有 vector 聚成 100 个簇,query 跟 100 个质心比,只在最近的 5 个簇里精搜。

| 维度 | HNSW | IVF |
|---|---|---|
| 召回率 | >95% | ~85-90% |
| 查询速度 | 快 | 中 |
| 写入速度 | 中 | 快 |
| 内存占用 | 高 | 低 |
| 适合 | 小-中规模、读多写少 | 超大规模 |

我们选 HNSW:规模小内存不是问题,读 100 : 写 1 适合 HNSW,user model 不允许漏。

---

## §2.4 · LLM + Embedding

### 决策

| 用途 | 模型 | 提供商 | 接入 |
|---|---|---|---|
| Chat LLM | `deepseek-chat` | DeepSeek | OpenAI 兼容 API |
| Embedding | `text-embedding-v3`(1024 维) | 阿里通义(dashscope) | OpenAI 兼容 API |

两个都走 OpenAI-compatible 端口,用 LangChain `ChatOpenAI` / `OpenAIEmbeddings` 一套接口,**换 provider 只改 .env 不动代码**。

### 为啥 DeepSeek

| 选项 | 取舍 |
|---|---|
| DeepSeek | 有免费额度;OpenAI 兼容;中文好;**比 GPT-4o 便宜 25-30 倍** |
| GPT-4o | 贵,开发期烧钱 |
| Claude Sonnet 4 | 贵 + 国内访问需翻墙 |
| 本地 Ollama | 7B 模型跑 ReAct loop 笨,agent 调度需要够大模型 |

成本:DeepSeek 跑一次 Awake `remember` ~$0.0006,GPT-4o ~$0.015。dogfood 50 次 / 天 DeepSeek 几分钱,GPT-4o 1 美刀。

### 为啥阿里通义 embedding

**关键背景**:**DeepSeek 没有 embedding 模型**——很多人不知道。

| 选项 | 取舍 |
|---|---|
| 阿里通义 text-embedding-v3 | 1024 维,OpenAI 兼容端口,国内付款,免费额度 |
| OpenAI text-embedding-3-small | 1536 维,要美元卡,demo 时国内不稳 |
| BGE-m3 本地 | 开源最强,但要 GPU + sentence-transformers |

### 代码

```python
@lru_cache(maxsize=1)
def get_chat_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
    )
```

三个细节:

1. **`@lru_cache(maxsize=1)`**:把 client 缓存成 singleton,避免每次重建 TCP / SSL
2. **`base_url=...`**:OpenAI 协议事实标准,重定向就调 DeepSeek
3. **temperature**:Awake 全部 + Sleep plan/consolidate/promote/demote/resolve 用 0.0(严格 JSON);Sleep **reflect 用 0.3**(自然语言段落要点变化)

### §2.4 · Q&A

#### Q1:什么是 chat LLM?ChatOpenAI 是怎么回事?

**LLM 分几种**(按接口):

| 类型 | 输入 | 输出 | 例子 |
|---|---|---|---|
| **Chat LLM** | 一组 message(role=user/assistant/system) | 下一句 assistant 回复 | GPT-4o, DeepSeek-chat, Claude |
| Completion LLM(老式) | 一段文本 | 文本续写 | text-davinci-003(已下架) |
| Embedding LLM | 一段文本 | 浮点数组 | text-embedding-v3 |

`deepseek-chat` 里的 "chat" 就是"对话型接口"。

**`ChatOpenAI` 是个命名陷阱**——这个 LangChain 类**名字带 OpenAI,但能调任何"实现 OpenAI HTTP 协议"的 LLM**。

**OpenAI-compatible API 的含义**:OpenAI 发模型时顺便发了 HTTP API 规范:
```
POST https://api.openai.com/v1/chat/completions
{ "model": "gpt-4o", "messages": [...], "temperature": 0.0 }
```

这套协议被行业当成事实标准。DeepSeek / Qwen / 阿里通义 / Mistral / 本地 vLLM 都**实现了这套协议**——换 URL 就能调,业务代码不变。

类比:**USB-C 充电器**——协议是 USB-IF 定的,但充电器能充任何支持 USB-C 的设备。`ChatOpenAI` 同理:它能调任何 OpenAI-compatible 端口。

验证我们没给 OpenAI 付钱:`.env` 里只有 `DEEPSEEK_API_KEY` + `https://api.deepseek.com/v1`,所有流量打 DeepSeek。

面试加分句:
> "我用 LangChain `ChatOpenAI` + base_url 重定向,**完全避开 vendor lock-in**——换 LLM 厂只改 env,不动代码。"

#### Q2:temperature 是什么?为什么 reflect 用 0.3 其他都 0?

**一句话**:控制 LLM 输出**随机性**的旋钮。低 = 死板确定,高 = 发散随机。

**原理 —— 它在缩放"下一个词的概率分布"**:

LLM 生成每个 token 时,先给整个词表算一个概率分布(每个词的 logit),temperature 调整这个分布有多"尖锐":
- 把 logit **除以 T** 再 softmax
- **T 越小 → 分布越尖锐**(高概率词更高)→ 趋向"总选最可能那个"
- **T 越大 → 分布越平**(冷门词也有机会)→ 越随机发散

| T | 行为 | 类比 |
|---|---|---|
| **0** | 几乎总选概率最高的词,同输入→同输出(确定性) | 灌铅骰子,永远同一面 |
| **0.3**(reflect) | 略有变化,仍忠于高概率词 | 微微偏心骰子 |
| **1.0**(默认) | 按原始分布采样,自然变化 | 公平骰子 |
| **1.5+** | 冷门词频出,易胡说/幻觉 | 发散失控 |

名字来源:借物理统计力学(玻尔兹曼分布)——高温=粒子乱动=无序;低温=趋向最确定的最低能态。

**项目用法**:

| 哪里 | T | 为什么 |
|---|---|---|
| Awake 全程 | **0** | 可复现 + 严格按 prompt + tool 决策确定;压住"乱跳"的随机性来源 |
| Sleep plan/consolidate/promote/demote/resolve | **0** | 要输出**严格 JSON**,发散 = 格式坏 + 决策不稳 |
| Sleep reflect | **0.3** | 唯一例外——写**自然语言段落**,要一点措辞自然度 |

**为什么 reflect 是 0.3 不是 0**:T=0 会让段落死板机械、每次几乎一样;0.3 给一点语言流动性像人写的;但**不给到 0.7**,因为还要忠于事实不能瞎编(高温=幻觉风险)。**0.3 = 自然但不放飞**。

**三个误解点**:
1. **T=0 ≠ 绝对确定**:理论 argmax 确定,但实际 API 因浮点/并发/MoE 路由有微小抖动。工程上当确定性用,别假设 100% 复现。
2. **高温 ≠ 更聪明/更有创意**:只是更随机。事实任务高温 = 胡说。
3. **temperature 不改模型能力**:只改采样策略,不改模型知道什么。同模型 T=0 和 T=1 知识一样,只是"嘴严不严"。

(相关参数:`top_p`(核采样)是另一种控随机性方式——只从累积概率前 p 的词采。常和 temperature 配合,别混。)

> 话术:"temperature 是采样随机性旋钮——logit 除以 T 再 softmax,T 小尖锐趋确定,T 大平趋发散。Awake + Sleep 决策全用 T=0(要确定 + 严格 JSON),只有 reflect 用 0.3(自然语言要措辞流动但不放飞)。"

---

## §2.5 · 其他组件

### 1. FastMCP —— MCP 服务器框架

**MCP**(Model Context Protocol)= Anthropic 2024-11 出的协议,让 LLM agent 调外部 tool。我们项目就是被调的"右边那个"。

**FastMCP**:`mcp.server.fastmcp.FastMCP`,Anthropic 官方 Python SDK。装饰器风格:

```python
@mcp.tool()
async def remember(content: str, tags: list[str] | None = None, ...):
    """Store a fact about the user.
    ONLY call for cross-project user-level facts...
    """
    ...
```

**关键设计:docstring 就是 LLM 看到的 tool description**——`@mcp.tool()` 把函数 docstring 转成 MCP 协议的 tool spec 给 client LLM。所以 docstring 不是给人看的注释,是**给 Claude Code 端 LLM 看的提示词**。

面试加分句:"我把 docstring 既当文档又当 LLM prompt——MCP 协议的设计意图就是 self-describing tool。"

### 2. Starlette —— Web 框架

**Web 框架 = 接 HTTP 请求 → 路由到处理函数 → 返回响应 的脚手架**(类似 Java 的 Spring Boot)。

```
FastAPI (高层)         ≈ Spring Boot
   ↑ 基于
Starlette (轻量)       ≈ Spring MVC 核心
   ↑ 基于
ASGI (协议规范)        ≈ Servlet 规范
```

Python 主流 web 框架:Django(大而全,类 Spring Boot)、Flask(轻量)、**FastAPI**(现在最火,Pydantic + OpenAPI + async)、**Starlette**(FastAPI 的底层)、aiohttp / Sanic(老一辈,被 FastAPI 取代)。

**我们用 Starlette 不用 FastAPI 的原因**:项目根本没 REST endpoint(只挂 MCP + 一个 `/health`),FastAPI 那套 Pydantic / OpenAPI / 依赖注入用不上,**用 Starlette 反而干净**。

代码:
```python
app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/mcp", app=mcp.streamable_http_app()),  # ← MCP 整个挂这
    ],
    lifespan=lifespan,
)
```

**lifespan**:`yield` 之前 = 启动钩子(scheduler、DB pool 初始化),之后 = 关闭钩子。

### 3. APScheduler —— 定时任务

`AsyncIOScheduler`(async 版)。两个触发器:

1. **idle 检测**:每 60 秒 tick,若 30 分钟无活动 → 触发 sleep cycle
2. **cron 兜底**:每天 03:00 强制跑一次

```python
sched.add_job(
    _idle_tick,
    trigger=IntervalTrigger(seconds=60),
    max_instances=1,        # ← 防重叠
    coalesce=True,          # ← 错过几次合并成一次
)
sched.add_job(
    _cron_tick,
    trigger=CronTrigger(hour=3),
    ...
)
```

`max_instances=1` + `coalesce=True` 是**容错设计**:上次没跑完不重叠,错过多次不堆排。

### 4. SQLAlchemy 2.0(async) + asyncpg

**ORM**(Object-Relational Mapping)= 把数据库表当 Python 类操作。**SQLAlchemy = Python 世界的 Hibernate**。

`Mapped[]` 是 2.0 新写法:
```python
class CoreBlock(Base):
    __tablename__ = "core_blocks"
    label: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    ...
```

IDE 完全识别字段类型,对齐 JPA + Lombok 体验。

**asyncpg**:PG 的 async 驱动(对应 Java 的 r2dbc-postgresql)。URL `postgresql+asyncpg://...` 让 SQLAlchemy 用它。

**关键混用**:SQLAlchemy 支持 ORM 风格也支持 Core 裸 SQL。我们项目两种都用:
- 简单 CRUD 走 ORM(`session.add(...)`)
- 复杂查询走 Core(`session.execute(text("SELECT ..."))`)

这是 SQLAlchemy 比 Hibernate 受欢迎的原因(后者混用难)。

### 5. pydantic-settings —— 配置管理

读 `.env` 文件 + 环境变量,**类型校验**进 `Settings` 对象。

```python
class Settings(BaseSettings):
    deepseek_api_key: str                       # ← 必填,启动时校验
    sleep_idle_threshold_seconds: int = 1800    # ← 自动转 int
    ...

settings = Settings()
```

类比 Spring `@ConfigurationProperties` + Bean 校验。`.env` 少配置启动直接失败,不是跑到一半 None。

### §2.5 · Q&A

#### Q1:Web 框架是啥?FastAPI 我没印象?

Web 框架就是 Python 版的 Spring Boot 同类物——接 HTTP 请求 → 路由 → 返回响应。

| Python 框架 | 类比 Java |
|---|---|
| Django | 类 Spring Boot 大全套 |
| Flask | 类老式 Spring MVC |
| **FastAPI** | 类 Spring Boot + 更现代(现在最火) |
| **Starlette** | FastAPI 的底层 |

FastAPI 长这样(对比 Spring Controller):
```python
@app.get("/users/{user_id}")        # ≈ @GetMapping("/{id}")
async def get_user(user_id: int):
    return await user_service.find_by_id(user_id)

@app.post("/users")                  # ≈ @PostMapping
async def create(dto: UserDto):     # Pydantic 自动校验 ≈ @Valid
    return await user_service.create(dto)
```

我们项目没 REST,所以用底层 Starlette。

#### Q2:SQLAlchemy 是啥?

ORM = 把表当对象操作,不用手写 SQL。**SQLAlchemy = Python 的 Hibernate**。

```python
# 定义实体(≈ @Entity)
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)

# 操作(≈ EntityManager)
async with session_factory()() as session:
    user = await session.get(User, 123)         # ≈ repo.findById(123)
    user.name = "new"
    await session.commit()                       # ≈ UPDATE 自动跑
```

#### Q3:Hibernate / JPA 是什么(只熟 MyBatis)?

```
Spring Data JPA              ← Spring 包装,提供 Repository 接口
   ↓ 基于
JPA (规范)                    ← 定义 @Entity / @Id / EntityManager
   ↓ 实现
Hibernate                     ← JPA 的具体实现,生成 SQL
```

跟 MyBatis 核心区别:**MyBatis 你写 SQL(半 ORM),JPA/Hibernate 框架生成 SQL(全 ORM)**。

| | MyBatis | JPA / Hibernate |
|---|---|---|
| SQL | 自己写 | 框架生成 |
| 简单 CRUD | 啰嗦 | 极爽 |
| 复杂查询 | 顺手 | 难 |
| 性能调优 | 容易 | 难 |
| 流行 | 中国 / 东亚 | 欧美 / 全球 |

**SQLAlchemy = 全 ORM,但也能像 MyBatis 那样裸跑 SQL**——这是它比 Hibernate 灵活的地方。我们项目两种风格混用(`memory/store.py` 走 ORM,`sleep/tools.py` 走裸 SQL)。

#### Q4:总之就是比 MyBatis 自动化的操作数据库手段?

对,核心就是这个。补两点 nuance:

1. "更自动化" + "更黑盒" 的权衡——节省样板代码同时失去 SQL 控制权
2. **SQLAlchemy 两种模式都支持**——简单 CRUD 走 ORM 省事,复杂查询走裸 SQL 可控。MyBatis 没法反过来(只会"半 ORM")

精确版:**JPA / Hibernate / SQLAlchemy = 比 MyBatis 更自动化(SQL 框架生成),但更黑盒(性能调优难)。SQLAlchemy 比另外俩灵活之处是支持两种模式混用。**

---

## §2 章末小结

| 维度 | 决策 | 关键理由 |
|---|---|---|
| 语言 | Python | AI agent 生态主场 |
| Agent 框架 | LangGraph(ReAct + StateGraph) | 行业标准 + 两种 API 适配两种 agent |
| DB | PG + pgvector | 关系 + 向量同库,HNSW 索引 |
| Chat LLM | DeepSeek(OpenAI 兼容) | 便宜 + 中文好 |
| Embedding | 阿里通义 v3 | DeepSeek 没 embedding |
| MCP server | FastMCP | Anthropic 官方,装饰器风格 |
| Web 框架 | Starlette | 没 REST 不上 FastAPI |
| Scheduler | APScheduler AsyncIO | idle + cron 双触发 |
| ORM | SQLAlchemy 2.0 async | Mapped[] 类型化,async session |
| Config | pydantic-settings | 启动时校验 |

---

# §3 · 架构(4 层)

## §3.0 · 全景图

```
                          ╔═════════════════════════════════╗
                          ║         Claude Code             ║
                          ║   (MCP host;终端 / IDE)         ║
                          ╚════════════╤════════════════════╝
                                       │ MCP over streamable-http
                                       │ (POST localhost:8000/mcp)
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  ① MCP Server 层  (mcp_server.py + main.py)                 │    │
│  │     - Starlette 挂载 /mcp + /health                          │    │
│  │     - FastMCP 暴露 4 个 tool:                                │    │
│  │       remember / recall / list_memory / forget               │    │
│  │     - 每个 tool 把 MCP 调用 → 自然语言 command → run_awake()  │    │
│  │     - mark_awake_activity() ← idle 计时重置                   │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
│                             │ command: "remember this fact: ..."    │
│                             ▼                                        │
│  ┌──────────────────────────────────┐  ┌──────────────────────────┐│
│  │  ② Agent 层 / Awake               │  │  ② Agent 层 / Sleep      ││
│  │  (awake/agent.py + tools.py)      │  │  (sleep/agent.py +       ││
│  │                                    │  │   scheduler.py + ...)    ││
│  │  - LangGraph create_react_agent    │  │  - LangGraph StateGraph  ││
│  │  - ReAct loop                      │  │  - 8-phase pipeline      ││
│  │  - Tools: load_core / search_      │  │  - APScheduler 触发      ││
│  │    archival / insert_archival /    │  │    (idle 30min + 03:00)  ││
│  │    get_overview / forget_archival  │  │  - run_sleep_cycle()     ││
│  │                                    │  │                          ││
│  │  POLICY: read core / write archival│  │  POLICY: sole writer of  ││
│  │                                    │  │   core_blocks            ││
│  └────────────────┬──────────────────┘  └────────────┬─────────────┘│
│                   │                                   │              │
│                   │  actor="awake_agent"              │  actor="sleep│
│                   │                                   │   _agent"    │
│                   ▼                                   ▼              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ③ Memory Store 层  (memory/store.py + sleep/tools.py)      │    │
│  │                                                              │    │
│  │  - list_core_blocks / semantic_search_archival (read)        │    │
│  │  - insert_archival / soft_delete_archival (awake write)      │    │
│  │  - write_core_block (sleep-only write,带 policy 检查)        │    │
│  │  - 所有 mutation 写 memory_ops_log(审计)                     │    │
│  │  - PermissionError if non-sleep actor 试图写 core           │    │
│  │  - Staging swap helpers (sleep/staging.py)                  │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │ SQLAlchemy async session            │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ④ Persistence 层  (db/models.py + asyncpg + PG)            │    │
│  │                                                              │    │
│  │  - PostgreSQL 16 + pgvector extension                        │    │
│  │  - 3 张主表:                                                  │    │
│  │      core_blocks       (5 行,固定 label)                     │    │
│  │      archival_facts    (向量 1024 维 + HNSW 索引)            │    │
│  │      memory_ops_log    (append-only 审计)                   │    │
│  │  - 2 张 staging 表(sleep cycle 期间存在):                    │    │
│  │      core_blocks_staging                                     │    │
│  │      archival_facts_staging                                  │    │
│  │  - 连接池:pool_size=10, max_overflow=5                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  dream Memory Service(单进程,~/dream 项目)                          │
└─────────────────────────────────────────────────────────────────────┘
```

## §3.1 · ① MCP Server 层

**职责**:面对 Claude Code,翻译 MCP 协议进出。

**关键文件**:`mcp_server.py`(4 个 `@mcp.tool()` 函数)+ `main.py`(Starlette app + lifespan + 挂载 `/mcp`)。

**核心动作**:每个 MCP tool 调用进来,把参数包成**自然语言 command**,交给 Awake agent 处理。**MCP 层本身不做业务判断,只负责协议翻译**。

**关键 side-effect**:`mark_awake_activity()` 在每个 tool 入口调一次,把 idle 计时归零——这是 Sleep 触发器的数据源。

## §3.2 · ② Agent 层

两个 agent 并存,**生命周期不重叠**:

### Awake(响应式)
- 触发:MCP tool call
- 运行:LangGraph `create_react_agent` ReAct loop
- 耗时:秒级
- 权限:读 core / 读写 archival,**绝不写 core**

### Sleep(自主)
- 触发:APScheduler 检测 idle ≥ 30 分钟,或每天 03:00 cron
- 运行:LangGraph `StateGraph` 8 阶段 pipeline
- 耗时:分钟级(预算 5 分钟)
- 权限:**core_blocks 的唯一 writer**

## §3.3 · ③ Memory Store 层

**职责**:**唯一的 DB 入口**——所有 agent 读写 memory 都过这一层。

**关键文件**:`memory/store.py`(公共 CRUD)+ `sleep/tools.py`(Sleep-specific 操作)+ `sleep/staging.py`(snapshot / atomic_swap / cleanup)。

**核心约束:`actor` 参数贯穿所有写操作**——

```python
async def insert_archival(session, ..., actor: Actor, ...): ...
async def write_core_block(session, ..., actor: Actor, ...): ...
```

`actor` ∈ `{"awake_agent", "sleep_agent"}`,应用层强制 check:

```python
# memory/store.py:245-259
if actor != "sleep_agent":
    session.add(MemoryOpsLog(op_type="policy_violation", ...))
    await session.commit()
    raise PermissionError(...)
```

→ **任何 Awake 试图写 core_blocks 的代码会被拒 + 留审计 + 抛异常**。这是 Letta read-only primary 的执行层保障。

## §3.4 · ④ Persistence 层

**职责**:数据落盘 + 向量检索。

**关键文件**:`db/models.py`(SQLAlchemy 2.0 declarative + engine + sessionmaker)+ `db/schema.sql`(DDL)。

**3 张主表**:

| 表 | 行数量级 | 谁能写 |
|---|---|---|
| `core_blocks` | 5 行(固定 label) | **只有 sleep_agent** |
| `archival_facts` | 1k-10k 行 | awake 写新 + sleep 改 |
| `memory_ops_log` | append-only 审计 | 所有写都留痕 |

**2 张 staging 表**(sleep cycle 期间临时存在):

| 表 | 何时存在 | 用途 |
|---|---|---|
| `core_blocks_staging` | snapshot → swap 之间 | Sleep 工作区,不影响主表 |
| `archival_facts_staging` | 同上 | 同上 |

## §3.5 · 跨层不变量(invariants)

| Invariant | 在哪强制 |
|---|---|
| 只有 sleep_agent 能写 core_blocks | `memory/store.py:245` 应用层 check |
| 每次 mutation 必须留 memory_ops_log | `memory/store.py` + `sleep/tools.py` 各写函数 |
| 同时最多一个 sleep cycle 跑 | `sleep/scheduler.py:44-47` `_cycle_running` flag + `max_instances=1` |
| Sleep 全程操作 staging 表,不动主表 | `sleep/tools.py` 所有 UPDATE 写 `_staging` 表 |
| Awake 操作完立刻 `mark_awake_activity` | `mcp_server.py:25` 在 `run_awake` wrap 里调一次 |
| staging swap 在单 transaction 完成 | `sleep/staging.py:80-92` 三对 RENAME 在同一 session |

记住这 6 条 = 80% 面试问题能答上。

## §3.6 · 一句话总结架构

> **MCP 层翻译协议 → Awake 实时响应 / Sleep 后台 consolidation → Memory Store 强制权限 + 留审计 → PG + pgvector + staging swap 落盘**。
>
> 核心设计哲学:**严格 read/write 分离 + Sleep 是 core 唯一 writer + Staging swap 保证并发安全**。

## §3 · Q&A

### Q1:MCP server 把参数转自然语言交给 Awake 走 ReAct,这么总结对吗?

大体对,但要点出关键细节:**这里有两个 LLM 在跑**。

```
Claude Code (LLM A, 比如 Claude Sonnet)
   ↓ 用户说"记一下我喜欢 4 空格"
   ↓ LLM A 决定调 MCP tool: remember(content="...", ...)
   ↓ HTTP POST 到 localhost:8000/mcp
                            ↓
  MCP server 接收
   ↓ 包装成 command: "remember this fact about the user: ..."
   ↓ 交给 run_awake(command)
                            ↓
  Awake agent (LangGraph ReAct, LLM B = DeepSeek)
   ↓ LLM B 看到 command + tool 列表
   ↓ ReAct loop: search → insert → done
   ↓ 返回结构化结果
                            ↓
  MCP server 返回给 Claude Code
                            ↓
  LLM A 看到结果,告诉用户"已记住"
```

**两个 LLM 互不知道对方**:LLM A 只看 MCP 协议响应;LLM B 只看包装的 command。

为啥分两层:权限 check + dedup + 持久化决策**不能让 client LLM 跑**——必须 server 端做。

### Q2:Sleep 8 阶段每个具体干啥?

| # | 阶段 | 干啥 | 关键文件 |
|---|---|---|---|
| 1 | **snapshot** | 主表整表复制到 staging,记 `snapshot_ts` | `sleep/staging.py:38-58` |
| 2 | **plan** | LLM 看状态决定本轮跑哪几个 phase(省 token + 跳无意义阶段) | `sleep/agent.py:106-127` |
| 3 | **consolidate** | pgvector 找 cosine < 0.15 的 cluster,LLM merge | `sleep/tools.py:92-151, 211-246` |
| 4 | **promote** | 找 `use_count≥5 AND confidence=3` archival,LLM 升到 core block(**core 唯一入口**) | `sleep/tools.py:154-178, 249-283` |
| 5 | **demote** | `confidence=1 AND last_used>90d` 软删 | `sleep/tools.py:181-203, 286-315` |
| 6 | **resolve** | LLM 扫 core 找内部矛盾(真逻辑冲突,不 fix 风格差异) | `sleep/agent.py:189-216` |
| 7 | **reflect** | LLM 写 2-4 句"about user"段落到 ops_log(给人审阅;唯一 T=0.3) | `sleep/agent.py:219-245` |
| 8 | **swap** | 单 transaction:合并 cycle 期间主表新 archival + 三对 RENAME + TRUNCATE 旧 | `sleep/staging.py:61-92` |

一图总结:
```
1.snapshot   = 复制主表 → staging        (DB)
2.plan       = LLM 决定本轮干啥          (LLM)
3.consolidate= LLM 合并重复 archival     (LLM + staging 写)
4.promote    = LLM 升 archival → core    (LLM + staging 写)  ← core 唯一入口
5.demote     = LLM 软删 stale            (LLM + staging 写)
6.resolve    = LLM 修 core 内矛盾         (LLM + staging 写)
7.reflect    = LLM 写 about-user 段落    (LLM + ops_log 写)
8.swap       = staging ↔ 主表 原子交换   (DB)
```

### Q3:Awake 和 Sleep 都要走 staging swap 吗?

**不。只有 Sleep 走 staging swap。Awake 直接写主表**。

| | Awake | Sleep |
|---|---|---|
| 单次耗时 | 秒级 | 分钟级 |
| 单次写量 | 1-2 行 | 几十-几百行 |
| 需要原子? | 不(单 INSERT 已 atomic) | **需要**(几十次写全成或全回滚) |
| 需要不阻塞读? | 不 | **需要**(Awake 期间还要 read/write) |

代码验证:
- `awake/tools.py` 的 `insert_archival_fact` → `memory/store.py:141-179` 的 `insert_archival` → 直接 `session.add(ArchivalFact(...))` + commit 到主表
- `sleep/tools.py:211-246` 的 `apply_consolidation` → `UPDATE archival_facts_staging` 只写 staging

**Awake 永远写主表,Sleep 永远写 staging**。

### Q4:Memory 和 Persistence 的区别就是一个查权限一个落库?

方向对,但 Memory Store 还干了别的:

| 层 | 职责 |
|---|---|
| **Memory Store** | (1) 权限 check (2) **业务原子操作**(`insert_archival` 干了"插行 + 算 embedding + 写日志"3 件事)(3) 审计日志 (4) 给上层**业务语义 API**(不是 raw SQL) |
| **Persistence** | (1) Schema 定义 (2) 连接池 (3) async 驱动 (4) **不知道任何业务规则** |

类比 Spring:
- Memory Store ≈ **Service 层**(`@Service` + `@PreAuthorize` + `@Transactional` + 业务方法)
- Persistence ≈ **Repository + 实体 + DataSource**

精确版:**Persistence = 表 + 连接 + 驱动(不懂业务);Memory Store = 业务语义 + 权限规则 + 审计**。Agent 永远只调 Memory Store。

### Q5:invariants 有对应文件吗?

**没有"invariants.py" 集中文件,分散在 6 处靠应用层 check + 程序员自律**。

| Invariant | 强制位置 | 怎么强制 |
|---|---|---|
| 只有 sleep_agent 能写 core | `memory/store.py:245-259` | 运行时 if + 抛 `PermissionError` + 留违规日志 |
| 每次 mutation 留 ops_log | `memory/store.py` + `sleep/tools.py` 各写函数 | 每个写操作里手动 `session.add(MemoryOpsLog(...))` |
| 同时最多一个 sleep cycle | `sleep/scheduler.py:44-47` `_cycle_running` flag + APScheduler `max_instances=1` | 布尔 + 框架配置 |
| Sleep 全程写 staging | `sleep/tools.py` 所有 UPDATE 拼 `_staging` 后缀 | **靠程序员自律**(没运行时阻止) |
| Awake 操作完调 mark_awake_activity | `mcp_server.py:25` 的 `run_awake` wrapper | 一处 wrap 所有 MCP tool |
| staging swap 单 transaction | `sleep/staging.py:61-92` | 全在一个 session 最后一次 commit |

**这是工程弱点**:invariant 散在 6 个文件,新写代码忘了规范就静默破坏。MVP 没单测验证这些。

**面试加分:诚实承认 + 给改进方向**:

> "MVP 阶段 invariant 强制是分散的,靠 code review + 自律。生产化要做:
> 1. **Repository 层 wrap**:Sleep 所有写经 `StagingRepository`,只暴露 staging 表 API,结构上不可能写主表
> 2. **AOP / 装饰器**:mutation 函数加 `@audit_logged`,自动写 ops_log
> 3. **架构测试**:跑 import-linter,验证 `sleep/*.py` 不能 import 主表写操作
> 4. **Schema-level**:用 PG row-level security (RLS),DB 层强制 Awake 角色不能 UPDATE core_blocks——终极保险"

这是 senior 级别思考。

---

# §4 · 数据模型

> 重点不是"表里有啥字段"——schema 一看就懂。重点是**每个字段为啥必须存在**,以及**没有的字段为啥故意不存**。

---

## §4.0 · 总览(3 主 + 2 staging)

```
┌─────────────────────────────────────────────────────────────┐
│  主表(常驻)                                                │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐│
│  │  core_blocks │  │  archival_facts   │  │ memory_ops_log ││
│  │  5 行固定    │  │  1k-10k 行 + 向量 │  │ append-only    ││
│  │  PK: label   │  │  PK: id(自增)   │  │ PK: id(自增)  ││
│  │              │  │                   │  │                ││
│  │  Sleep 唯一  │  │  Awake 写新行     │  │ 所有 mutation  ││
│  │  writer      │  │  Sleep 改 / 软删  │  │ 留痕(谁/啥/原因) ││
│  └──────────────┘  └──────────────────┘  └────────────────┘│
│                                                              │
│  Staging 表(仅 sleep cycle 期间存在)                       │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │ core_blocks_staging     │  │ archival_facts_staging  │  │
│  │ (LIKE core_blocks)      │  │ (LIKE archival_facts)   │  │
│  │ Sleep 写到这,跑完 swap │  │ 同左                    │  │
│  └─────────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**为什么是这 5 张不是 3 张或 8 张**:

| 想法 | 为啥不做 |
|---|---|
| "core 和 archival 合一张表加 type 字段" | 字段差太多(core 有 char_limit / version,archival 有 embedding / use_count / is_deleted)→ 一半字段是 NULL,索引也得分情况 |
| "ops_log 按月分表" | MVP 一年也就几万行,分表是过度设计 |
| "staging 不要 2 张,在主表上加 staging_id" | 实施时所有读 / 写都要带 `WHERE staging_id IS NULL`,代码污染严重 + 索引行为难预测 |
| "再加一张 users 表" | MVP 单用户 `user_id="userjyx"` 写死;真要 multi-tenant 那时再加 + 全表加 user_id 列 |

→ **3 主 + 2 staging 是 Letta paper + 我们 scope 的最小集**。

---

## §4.1 · `core_blocks` —— 5 张便签

### Schema

```sql
CREATE TABLE core_blocks (
    label         TEXT PRIMARY KEY,                  -- ← 5 个固定 label
    value         TEXT NOT NULL,                     -- ← 块内容,自由文本
    char_limit    INT  NOT NULL DEFAULT 2000,        -- ← 块大小上限
    version       INT  NOT NULL DEFAULT 1,           -- ← 版本号
    last_writer   TEXT NOT NULL DEFAULT 'sleep_agent', -- ← 自检字段
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 启动预填(永远只有这 5 行,label 不增不减)
INSERT INTO core_blocks (label, value) VALUES
    ('background',      ''),
    ('preferences',     ''),
    ('habits',          ''),
    ('skills',          ''),
    ('lessons_learned', '')
ON CONFLICT (label) DO NOTHING;
```

### 5 个 label 的语义分工

| label | 装啥 | 例子 |
|---|---|---|
| `background` | 身份 + 客观事实 | "Java 后端实习,Thunderbit,在求职" |
| `preferences` | 风格偏好 | "4 空格,具名函数 > inline lambda,先写测试" |
| `habits` | 行为模式 | "习惯在 docs/ 下记 bug-fix 报告" |
| `skills` | 能力盘点 | "Java 强 / Python 中等 / React 弱" |
| `lessons_learned` | 教训库 | "asyncio.gather 嵌 for loop 会死锁" |

→ **不是按主题随便分,是按"agent 怎么用这块信息"分**:
- `background` 影响**称呼 / 任务理解**(你是后端,我不该解释 HTTP)
- `preferences` 影响**代码风格输出**
- `habits` 影响**默认行为**(知道你在 docs/ 记报告就主动放那)
- `skills` 影响**讲解深度**
- `lessons_learned` 影响**避坑提醒**

### 字段逐个剖

#### `label TEXT PRIMARY KEY` —— 不是自增 id

**反常识**:主键用文本不用自增 int。

为啥:
1. 这 5 个 label **永远固定**,自增 id 没意义
2. PK = label 后,所有 query 直接 `WHERE label = 'preferences'`,**index seek 一次到位**
3. 跨服务时 label **天然可读** → 日志 / 监控更直观

→ "如果 schema 永远只有有限几个候选键,文本主键 > 自增 id" 这是个通用经验。

#### `value TEXT NOT NULL` —— 整块字符串

存的不是 JSON,是**自然语言段落**。给 LLM 看的格式。

例子(`preferences` 的 value):
```
User prefers 4-space indent in Python/Java/TypeScript.
Prefers named functions over inline lambdas (readability).
Writes tests first when adding new public APIs.
Avoids over-mocking in tests — likes real-DB integration tests.
```

为啥不结构化:
- LLM 读自然语言成本最低,**额外结构反而限制 Sleep 写入的灵活性**
- Letta paper 明确把 core block 设计成自由文本

#### `char_limit INT DEFAULT 2000` —— 强制写紧

Sleep promote 时 prompt 里强制:`new_block_value MUST be ≤ char_limit`。

为啥要限:
1. **防止 core 长成大杂烩** → 失去"5 张便签"的精炼意义
2. **每次 Awake 全量加载** → 不限大小 context 一次塞 50KB
3. **强制 Sleep 做选择** → 满了就必须取舍,LLM 不能 lazy 全加

2000 不是拍的:5 块 × 2000 字符 ≈ 10 KB ≈ **2-3K tokens**,Awake 每次都全加进 system context 都不痛。

#### `version INT DEFAULT 1` —— 单调递增

Sleep 每次成功 `write_core_block` → `version += 1`。

用途:
1. **乐观锁**(MVP 未启用,留接口):`UPDATE ... WHERE version = ?` 防止覆盖
2. **跨 cycle 比对**:reflect 阶段如果想"自上次 cycle 后 preferences 变了几次",查 version 差
3. **审计可追**:`memory_ops_log` 里 `target_id = "preferences:v3"` 比 `target_id = "preferences"` 信息更多

#### `last_writer TEXT DEFAULT 'sleep_agent'` —— 自检兜底

每次写入填当前 actor。**正常情况永远是 `sleep_agent`**。

```sql
SELECT label, last_writer FROM core_blocks WHERE last_writer != 'sleep_agent';
```

→ 任何一行不是 `sleep_agent` = **应用层 invariant 被绕过了**,要立即报警。**最后一道防线**。

(应用层在 `memory/store.py:245` 已经拦了,但万一有人新加路径忘了 check,`last_writer` 能在 DB 里看出来。**纵深防御**。)

#### `updated_at TIMESTAMPTZ DEFAULT now()` —— PG 自动填

`TIMESTAMPTZ`(带时区)>= `TIMESTAMP`(不带)。PG 推荐用 TZ 版,避免跨时区部署混乱。

### 故意不存的字段

| 想加的 | 为啥不加 |
|---|---|
| `id` 自增 | label 已经是 PK,自增 id 多余 |
| `user_id` | MVP 单用户,multi-tenant 那时再加 |
| `embedding` | core 永远 5 条全读,不需要 ANN 检索 |
| `created_at` | core 块永远存在(预填),只有 `updated_at` 有意义 |
| `is_deleted` | core 块不能软删,只能改 value(label 永远固定) |
| `tags` | core 已经按 label 分类,tags 重复 |

**面试加分句**:"core_blocks 的设计哲学是**约束驱动**——固定 label / 字符上限 / version / last_writer,每个字段在防一种 anti-pattern。比 schema 自由的方案更难做错。"

### §4.1 · Q&A

#### Q1:面试官追问"5 个 label 是 Letta paper 给的还是你拍的"怎么答?

**答**:阅读了 Letta paper 里 core memory block 的抽象,认为其分类合理(粒度刚好够覆盖一个用户画像 + 不至于碎),所以直接采用。

→ 这是个**有思考的采用**,不是"我自己拍的"也不是"我抄的"。面试官追问能展开说:"Letta 的 5 块在 agent 应用场景验证过,我项目 scope 一致,没必要重新发明。"

#### Q2:`last_writer` 这个自检字段有用吗?

**答**:有用——属于纵深防御。

应用层在 `memory/store.py:245` 已经拦了 99% 的非法写入,但万一:
- LLM 抽风(不太可能,但 prompt injection 已经发生过)
- 后续新加代码路径忘了走 `write_core_block`(开发疏忽)
- 内部 bug 绕过 actor check

→ DB 字段 `last_writer != 'sleep_agent'` 能**事后查出来**,虽然挡不住写入但能立即报警。**应用层挡 99% + DB 字段挡剩 1% + 留可观测**。

---

## §4.2 · `archival_facts` —— 自由 fact + 向量

> 这是项目里**字段最多 / 索引最复杂 / 决策最密集**的表。所有字段都在为两件事服务:**(1) 让 Awake 能快速语义检索**;**(2) 让 Sleep 有信号决定 promote / demote**。

### Schema

```sql
CREATE TABLE archival_facts (
    id            BIGSERIAL PRIMARY KEY,
    content       TEXT NOT NULL,
    tags          TEXT[],
    confidence    SMALLINT NOT NULL DEFAULT 2,
    source        TEXT,
    embedding     vector(1024),                  -- ← nullable
    is_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,                   -- ← nullable
    use_count     INT NOT NULL DEFAULT 0
);
```

### 字段逐个剖

#### `id BIGSERIAL PRIMARY KEY` —— 跟 core 反过来

| | core_blocks | archival_facts |
|---|---|---|
| PK | `label TEXT`(语义键) | `id BIGSERIAL`(自增) |
| 为啥 | label 固定 5 个 | fact 数量无上限,内容易重复 |

`BIGSERIAL` = `BIGINT + 自增`(Java 的 `long + AUTO_INCREMENT`)。**不用 INT 是因为预留**——一年攒万条,不会爆 INT,但宁可一开始大不抠门。

#### `content TEXT NOT NULL` —— fact 本体

自然语言一句话(40-200 字符典型)。

设计原则:**一条 fact = 一个原子事实**。
- ✅ "用户喜欢 4 空格"
- ❌ "用户喜欢 4 空格,而且偏好具名函数,而且先写测试" → 3 条 fact

为啥拆原子:Sleep consolidate / promote 是按行操作的,**合在一起的 fact 没法部分 promote / 部分 demote**。

#### `tags TEXT[]` —— 数组列(PG 特有)

PG 原生支持 array 列,**省得开第二张表**(MySQL 就得 `archival_tags(fact_id, tag)` 多对多)。

例子:`{"preference", "code-style", "indent"}`

用途:
1. **MCP `remember` 时由 Claude Code 端传入**(类目化)
2. **Awake `get_overview` 时按 tag 分组统计**("preference 类有 12 条")
3. **未来过滤检索**("只搜 lesson 类 fact")

#### `confidence SMALLINT DEFAULT 2` —— 1/2/3 三档

| 值 | 含义 | 例子 |
|---|---|---|
| 1 | low | "用户**可能**喜欢深色主题"(一次提到) |
| 2 | medium | "用户提到过几次 4 空格"(默认值) |
| 3 | high | "用户明确说过 'I prefer 4-space'" |

为啥不浮点 [0, 1]:
- LLM 输出整数比小数稳得多(prompt 里写 `"confidence": 1` vs `"confidence": 0.73`)
- 离散三档**够用**——超过 3 档 LLM 自己也分不清 0.7 跟 0.8 啥区别
- Sleep 阈值好写:promote 要 `confidence=3`,demote 容许 `confidence=1`,**整数 == 直接比**

#### `source TEXT` —— 来源标签

可选。典型值:
- `"awake:remember"`(MCP remember 触发)
- `"sleep:consolidate:merge_from_42_51"`(consolidate 合并产物)
- `"sleep:promote:demote_from_core_xxx"`(留种用)

用途:**审计 / debug**——"这条诡异 fact 是哪来的",查 source 一眼看到。

#### `embedding vector(1024)` —— **可空,故意的**

1024 维 = 阿里通义 text-embedding-v3 默认维度。

**Nullable 不是疏忽,是 defer-write 模式**:
1. `insert_archival` 先把行落地(content / tags / confidence)
2. **同步算 embedding** → 同事务 UPDATE 回去

```python
fact = ArchivalFact(content=..., embedding=None)  # ← 先落
session.add(fact)
await session.flush()                              # ← 拿到 id
fact.embedding = await embed_text(content)         # ← 再补
await session.commit()
```

为啥不一步:
- LLM API call(embedding)**可能失败 / 超时**
- 即使失败 fact 也要存住,**不能因为 embedding 挂了把 fact 也丢**
- 失败的行 `embedding IS NULL`,可以**后台批量补**

→ 这是个**容错设计**:语义检索是 nice-to-have,fact 存储是 must-have。**别为弱依赖污染强依赖**。

#### `is_deleted BOOLEAN DEFAULT FALSE` —— 软删

`forget` MCP tool 不真 DELETE,只 `UPDATE ... SET is_deleted=TRUE`。

为啥软删:
1. **可审计**:用户问"我以前是不是说过 X",软删的能查回
2. **可回退**:LLM 偶尔抽风误判删错,改 boolean 比从备份恢复快
3. **Sleep consolidate 的 "discarded_ids" 也走软删** → 留种以备 reflect

成本:`SELECT` 全部要带 `WHERE is_deleted = FALSE` → 用 partial index 化解(见下面索引部分)。

#### `created_at` + `last_used_at` + `use_count` —— **Sleep 的决策信号**

这三个字段**不是给 Awake 用的**,**是给 Sleep 看的**。

```
              ┌────────────────────────────────────────┐
              │  Sleep 怎么用这三个字段决定 promote / demote   │
              └────────────────────────────────────────┘

PROMOTE 候选:  use_count >= 5  AND  confidence = 3
              ↑ Awake search_archival 命中次数(说明常被用到)

DEMOTE 候选:   last_used_at < now() - 90 days  AND  confidence = 1
              ↑ 长期没被命中(说明 LLM 都不觉得相关)

REFLECT 时:    created_at DESC LIMIT 10 = "最近 fact 摘要"
```

**`use_count` 怎么变**:`semantic_search_archival` 命中后,Memory Store 自动 `UPDATE ... SET use_count = use_count + 1, last_used_at = now()`。**读操作有 side-effect**——这是个故意的设计,违反"读不改写"原则,但这是 Letta paper 推荐的"用 access pattern 信号驱动 consolidation"。

→ **每次 Awake `recall` 都在悄悄给 Sleep 喂数据**。

---

### 3 个索引(每个解决一个问题)

```sql
-- 索引 1:HNSW 向量检索
CREATE INDEX idx_archival_embedding
    ON archival_facts USING hnsw (embedding vector_cosine_ops);

-- 索引 2:GIN 数组检索
CREATE INDEX idx_archival_tags
    ON archival_facts USING GIN (tags);

-- 索引 3:partial 时间检索(只索引 active 行)
CREATE INDEX idx_archival_active
    ON archival_facts (is_deleted, created_at DESC)
    WHERE is_deleted = FALSE;
```

| 索引 | 服务的 query | 类型为啥这个 |
|---|---|---|
| `idx_archival_embedding` | `ORDER BY embedding <=> $1 LIMIT 5`(Awake recall) | HNSW = 分层图,1 万行级 ms 级返回,B-tree 不能索引 vector |
| `idx_archival_tags` | `WHERE tags && ARRAY['preference']`(按 tag 过滤) | GIN = Generalized Inverted Index,**专门给数组 / JSON 用**,B-tree 不能索引数组 |
| `idx_archival_active` | `WHERE is_deleted=FALSE ORDER BY created_at DESC`(reflect / 列表) | **partial index** = 只索引满足 WHERE 的行,**比全表索引小 10 倍**(假设 10% 软删),且 query optimizer 直接用 |

**partial index 是个高分点**,展开讲下:

普通索引会索引**所有行**(包括软删的)。但我们 99% query 都 `WHERE is_deleted=FALSE`,**软删的行被索引等于白索引**。Partial index 只对 active 行建索引:
- 索引文件**小**(假设 10% 软删,索引省 10% 空间)
- 写入**快**(软删行 UPDATE 不动这个索引)
- query optimizer **直接用**(`EXPLAIN` 里能看到 `Index Scan using idx_archival_active`)

**面试加分句**:"软删是高频 case,但**用 partial index 把 is_deleted 列变成索引谓词**,既能软删审计,又不付查询性能税。"

---

### 故意不存的字段

| 想加 | 为啥不加 |
|---|---|
| `user_id` | MVP 单用户 |
| `core_block_label`(FK 到 core) | **故意解耦**——archival 不该知道自己将来 promote 到哪块 core,那是 Sleep 决策时才定的 |
| `superseded_by`(指向 merge 后的 fact id) | 想加但**ops_log 里已经有这信息**——consolidate 的 `target_id="42→37"` 已经能查 |
| `embedding_model` 列(标记是哪个 embedding 模型) | **未来要换 embedding 模型时再加**,现在加是过度设计 |
| `lock_version`(乐观锁) | archival 写并发场景几乎不存在(Awake 串行 + Sleep 走 staging),省 |

---

### §4.2 · 小结

`archival_facts` 是项目里**信息密度最高的表**:
- `confidence` + `use_count` + `last_used_at` = **Sleep 的决策信号源**
- `embedding nullable` = **defer-write 容错**
- `is_deleted` + partial index = **软删但不付性能税**
- 3 个索引各管一类 query(vector / 数组 / 时序)

**一句话面试稿**:
> "archival_facts 的每个字段都有明确职责——content / tags 给 Awake 检索,confidence / use_count / last_used_at 给 Sleep 信号,embedding 可空容许 defer-write,is_deleted 加 partial index 实现零成本软删。"

---

### §4.2 · 课后思考题(已答 + 点评)

#### Q1:`use_count` 在**读操作**里被更新——违反 CQS(命令查询分离),你 OK 吗?

背景:`semantic_search_archival` 表面是个 SELECT,但内部跑完会 `UPDATE ... SET use_count = use_count + 1, last_used_at = now()`——**读操作有 side-effect**。

**用户回答**:可以接受,没必要分开;但不知道怎么辩护。

**点评 —— 辩护三件套(直觉对,补上论证)**:

辩护核心一句:**"这不是业务副作用,是遥测(telemetry)。"**

1. **区分"业务写" vs "统计写"**:CQS 反对的是查询时偷改**业务状态**(让读不可缓存、不可重试)。但 `use_count +1` 改的是**访问统计**,这类"读时遥测"行业到处都是,有名字:
   - 操作系统的 `atime`(读文件更新"最后访问时间")
   - 缓存的 LRU 计数(读 key 记录冷热)
   - CDN 命中计数
2. **CQS 本就有公认例外**:Martin Fowler(提出者)自己说 CQS 是指导原则不是铁律。`stack.pop()` 就是经典例外(既返回值又改状态)。访问计数同类。
3. **最终一致就够**:`use_count` 拿来做 `>= 5` 的模糊阈值判断,不是账务。并发下丢几次 +1(两个 recall 同时 UPDATE 互相覆盖),5 和 7 对"要不要 promote"是同一决定 → **不需要加锁、不需要精确**。为纯净去拆表反而 over-engineering。

**退路(显示你知道纯净方案存在)**:真要纯读,把信号 append 到独立 `access_log` 表,Sleep 聚合时 COUNT。但 MVP 没必要。

→ **完整话术**:"use_count 更新不是业务副作用是遥测信号——类比 OS 的 atime / 缓存 LRU 计数。CQS 本就有公认例外(stack.pop)。这个信号最终一致就够,丢几次不影响 Sleep 的模糊阈值判断,为纯净拆表反而 over-engineering。真要纯读我可以拆 access_log + COUNT,MVP 没必要。"

#### Q2:Partial index `WHERE is_deleted=FALSE` 你以前见过吗?

背景:**MySQL 8 之前不支持 partial index**。只做过 MyBatis + MySQL 大概率没见过。

**用户回答**:没做过,之前软删都建完整索引,不知道有什么坑。

**点评**:

完整索引**能跑,但没优化**——它把软删的死行也索引了,白占空间 + 拖慢写。partial 是进阶(只索引活行,假设 10% 软删省 10% 空间 + 写入快)。

**最大的坑 —— 谓词不匹配,索引白建**:

partial index 只有当 PG 能**证明** query 条件落在索引谓词范围内才会用它。

```sql
-- 索引建的是 WHERE is_deleted = FALSE

-- ✅ 用得上(硬编码 FALSE,planner 能证明)
SELECT * FROM archival_facts WHERE is_deleted = FALSE ORDER BY created_at DESC;

-- ❌ 用不上!(参数绑定 $1,plan 阶段不知道运行时传 FALSE 还是 TRUE)
SELECT * FROM archival_facts WHERE is_deleted = $1 ORDER BY created_at DESC;
```

第二种最容易踩——ORM / prepared statement 默认把值参数化成 `$1`。PG plan 阶段不知道 `$1` 是不是 FALSE → 为安全**不用这个 partial index** → 退回全表扫描。**你白建了还以为有优化,线上慢了都不知道为啥。**

**避坑**:
1. query 条件**硬编码** `WHERE is_deleted = FALSE`(别用参数)——这正是代码 `store.py:116` 写死 `.where(ArchivalFact.is_deleted.is_(False))` 的原因
2. 上线后 `EXPLAIN` 确认走了 `Index Scan using idx_archival_active` 而不是 `Seq Scan`

(次坑:索引的 `ORDER BY created_at DESC` 方向也得跟 query 一致,否则只能用于过滤不能用于排序。但谓词匹配是第一大坑。)

#### Q3:为什么 LLM 自报的「小数置信度」没意义?(讨论补录)

> 这是讲 `confidence` 字段引出的追问:为什么用离散 1/2/3 而不让 LLM 输出 0.73 这种小数。

**先纠正措辞**:不是"小数没意义",是**"让 LLM 在文本里自报的那个小数没意义"**。

1. **LLM 是"说"出 0.73,不是"算"出来的**:它根据训练数据里人类在类似语境写什么数字,**sample** 出一个 token。这个 0.73 是**模仿**出来的不是**测量**出来的,和"真实 73% 会对"没有可靠对应关系。
   - 关键概念:**校准(calibration)**——置信度有意义的前提是"它说 70% 的事真有约 70% 发生"。LLM 自报文本数字**没校准**。
   - 注意:模型内部确实有真实 token 概率(logits),那个有意义;但它在**正文里写出来**的 confidence 是 sample 结果,不是内省自己的概率。
2. **LLM 分不清 0.7 和 0.8**:同一 fact 打分 5 次会在 0.7~0.8 乱跳(抖动 = 噪音证据)。但分"低/中/高"5 次大概率同一档。**粗粒度稳,细粒度瞎编**。
3. **虚假精确(false precision)有害**:0.73 看起来精确,会诱导下游写 `if confidence > 0.72` 这种没依据的阈值。离散三档反而**诚实**:只声称能可靠区分的粒度。
4. **离散三档够用**:Sleep 用 confidence 做 `promote 要 3 / demote 容忍 1` 的粗判断,本来就不需要细粒度。

**误区澄清**:别因此以为"小数置信度都没用"。**有校准**的系统里小数很有用(分类器 softmax + temperature/Platt scaling;或 LLM 读 token logprobs 拿校准不确定性)。否定的是"让 LLM 正文瞎报小数"这个**做法**,不是"置信度用小数"这个**概念**。

→ **话术**:"不是小数没意义,是 LLM 正文自报的小数没校准、且超出它能稳定分辨的粒度——它是'说'出 0.73 不是'算'出来的,多问几次还会变。离散三档不假装有不存在的精度。真要可信小数得用 token logprobs + 校准,这是 MVP 之外的工程。"

---

## §4.3 · `memory_ops_log` —— append-only 审计日志

> 不是业务表,是**所有 mutation 的事后证据库**。设计哲学只有一条:**append-only + 永不修改**。一旦写进去,这条记录就是历史事实。

### Schema

```sql
CREATE TABLE memory_ops_log (
    id            BIGSERIAL PRIMARY KEY,
    op_type       TEXT NOT NULL,
    actor         TEXT NOT NULL,
    target_kind   TEXT,                  -- 'core' / 'archival' / NULL(reflect)
    target_id     TEXT,                  -- core label 或 archival id 转 text
    before_value  TEXT,
    after_value   TEXT,
    reason        TEXT,                  -- LLM 自由文本理由
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ops_log_ts    ON memory_ops_log(ts DESC);
CREATE INDEX idx_ops_log_actor ON memory_ops_log(actor, ts DESC);
```

### 8 种实际写入的 op_type

从 `memory/store.py:OpType` Literal 类型枚举 + `sleep/tools.py` 实际调用:

| # | op_type | 谁触发 | 啥时候插 | target_kind |
|---|---|---|---|---|
| 1 | `remember` | Awake | `insert_archival(actor='awake_agent')` | archival |
| 2 | `forget` | Awake | `soft_delete_archival(actor='awake_agent')` | archival |
| 3 | `sleep_consolidate` | Sleep | `apply_consolidation` + **`apply_resolutions` 也用这个**(MVP collapsed) | archival 或 core |
| 4 | `sleep_promote` | Sleep | `apply_promotions` | core |
| 5 | `sleep_demote` | Sleep | `apply_demotions` | archival |
| 6 | `sleep_reflect` | Sleep | `log_reflection`(写 about-user 段落) | NULL |
| 7 | `policy_violation` | 异常路径 | `write_core_block` 被 non-sleep actor 调时 | core |
| 8 | `recall` | 定义但**不写入** | hot path 不留 log | - |

**两个 known wart 要记牢**:

1. **`recall` 不写日志**——`semantic_search_archival` 是高频热路径,每次再插一行 ops_log 翻倍写放大。`mark_archival_used` 函数注释明确写 "No log (hot path)"。
2. **`apply_resolutions` 写 `sleep_consolidate`**——`sleep/tools.py:340` 注释 "resolve op_type collapsed under consolidate for MVP"。MVP 取舍,生产化要拆出独立 `sleep_resolve`。

### 字段逐个剖

#### `id BIGSERIAL` —— 单调时序

按时间单调递增,**等价于"事件序列号"**。"5 月 12 日的第 8 次写入" → `WHERE id BETWEEN ? AND ?`。

#### `op_type` + `actor` —— 二元分类

`op_type` 标"做了什么",`actor` 标"谁做的"。组合的实际语义:
- `(remember, awake_agent)` = Awake 应 MCP 请求写入新 fact
- `(sleep_promote, sleep_agent)` = Sleep 决定升 core
- `(policy_violation, awake_agent)` = **Awake 试图越权写 core → 立即报警条件**

→ `idx_ops_log_actor` 索引服务 "**按 actor 分轴 + 时间倒序**":
```sql
SELECT * FROM memory_ops_log
WHERE actor = 'sleep_agent' ORDER BY ts DESC LIMIT 100;
```

#### `target_kind` + `target_id` —— 多态指向

`target_kind ∈ {'core', 'archival', NULL}`,`target_id` 是字符串(因为 core PK 是文本 label,archival PK 是 int 但转 text 统一存)。

**反范式设计**——传统方案会拆 `ops_log_core` + `ops_log_archival` 两张表各加 FK。我们合一张表的理由:
- 审计查询 99% 想要"时间倒序所有 mutation",不在乎类型
- 合表后**只需一个 ts 索引**就能 timeline 查询
- 代价:`target_id TEXT` 失去 FK 约束 → 但 **ops_log 本来就要保留删除后的记录**,FK 反而碍事

#### `before_value` + `after_value` —— **存全文 diff,不是 unified diff**

例子(promote 第一次填充 `preferences`):
```
before_value: ""
after_value:  "User prefers 4-space indent..."
```

例子(consolidate 合并两条 archival):
```
before_value: NULL  (kept_id 不读旧值;实现简化)
after_value:  "merged content"
reason:       "Merged 2 duplicates; <LLM 给的理由>"
```

**为啥不存 diff**:
1. **审计场景人读** → 看全文 > 拼 diff
2. **存储成本可接受** → core 2KB × 几百次 = 几百 KB;archival 200B × 万次 = 几 MB;**一年个位 GB**
3. **简单** → 不依赖 diff 库,grep 可读

代价:**体积比 diff 方案大 5-10 倍**。生产化可改 unified-diff(详见 §7)。

#### `reason TEXT` —— LLM 强制解释

写入时**强制让 LLM 留理由**,典型例子:
```
reason: "Promoted from archival id=42: User mentioned 4-space indent
         8 times across sessions; high-confidence + high-use."
```

三个用途:
1. **诊断"为啥 core 变成这样"** → 不是黑盒
2. **Sleep `reflect` / `resolve` 读最近 20 条 ops_log 喂给 LLM**(`sleep/agent.py:195-211`)做 retrospective
3. **将来 fine-tune Sleep prompt 的 ground truth dataset**

### 索引设计

```sql
CREATE INDEX idx_ops_log_ts    ON memory_ops_log(ts DESC);
CREATE INDEX idx_ops_log_actor ON memory_ops_log(actor, ts DESC);
```

| 索引 | 服务的 query |
|---|---|
| `idx_ops_log_ts` | "最近发生啥" → `ORDER BY ts DESC LIMIT N` |
| `idx_ops_log_actor` | "Sleep / Awake 各自最近做啥" → 复合索引,`WHERE actor = ?` 走前缀,`ORDER BY ts DESC` 走后缀 |

**没有 `(op_type, ts DESC)` 索引**——因为 `op_type` 分布偏斜(`sleep_consolidate` 占 50%+),复合索引选择性差。未来想按类型查加单列 `idx_op_type` 即可。

### append-only 怎么保证?

**答案**:**应用层约定 + 没 DB 强制**。

具体:
- 代码层面**只 `session.add(MemoryOpsLog(...))`**,全 codebase **没有 `UPDATE` / `DELETE` ops_log**
- DB 层面**没有 trigger 阻止 UPDATE / DELETE**,任何人 `psql` 进去都能改

→ 又一个 **invariant 散落在应用层** 的例子(对应 §3.5 invariants 表)。

**生产化升级方向**:
```sql
CREATE OR REPLACE FUNCTION reject_modify_log() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'memory_ops_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_update BEFORE UPDATE ON memory_ops_log
    FOR EACH ROW EXECUTE FUNCTION reject_modify_log();
CREATE TRIGGER no_delete BEFORE DELETE ON memory_ops_log
    FOR EACH ROW EXECUTE FUNCTION reject_modify_log();
```

或更狠:`REVOKE UPDATE, DELETE ON memory_ops_log FROM app_user;`

→ **MVP 不做不是疏忽**:trigger 让 schema migration 痛苦 + 调试时报错丑。MVP 阶段**信任开发者纪律**。

### Sleep `resolve` / `reflect` 怎么用 ops_log

`sleep/agent.py:195-211` —— resolve 阶段读最近 20 条:
```python
recent = (await session.execute(sql_text(
    "SELECT op_type, actor, target_kind, target_id, reason, ts "
    "FROM memory_ops_log ORDER BY ts DESC LIMIT 20"
))).all()
```

LLM 看到最近 20 条 mutation 后,**有"最近发生了什么"的上下文**,resolve 不会孤立判断,能联想:"刚 promote 了一条 preferences,跟现有 habits 是不是冲突"。

→ **轻量 retrospective 机制**,比每次重新扫全表便宜得多。

### 为啥不分表 / 不归档

| 方案 | 为啥 MVP 不做 |
|---|---|
| 按月分表(`ops_log_202504` / `ops_log_202505`) | 一年才几万行,分表收益 < 运维成本 |
| PG declarative partitioning by ts | 同上,SQLAlchemy declarative ORM 跟 partitioning 集成有坑 |
| 老数据归档到 S3 / cold storage | 没业务诉求 |
| 触发器自动 compact / vacuum | PG `autovacuum` 默认开,够用 |

**临界点估算**:
- 行数到 100 万 → 单表查询还可以,INSERT 走 B-tree 索引开始变慢
- 行数到 1000 万 → 必须分表 / 归档
- 项目按当前预估 **5-10 年都到不了 100 万** → 现在做是过度设计

### §4.3 · 小结

`memory_ops_log` 不是业务表,是**给运维 + Sleep 的事后证据库**。3 个设计特点:
1. **append-only**(应用层约定,没 DB 强制 → 已知 trade-off)
2. **全文 before/after**(成本可控,审计可读)
3. **reason 字段强制 LLM 解释**(协同设计,不是黑盒)

**面试加分句**:
> "ops_log 设计上是**纵深防御 + 协同诊断**——纵深因为跟主表写在同一 transaction(§6 会展开),协同因为 reason 字段让 Sleep reflect 能做 retrospective,LLM 不是孤立决策。"

### §4.3 · 课后思考题

#### Q1:ops_log 是 append-only 但应用层只靠 INSERT 自律,DB 没强制——如果让你加强保证,你会怎么做?

提示:PG 至少 3 种武器:
- `BEFORE UPDATE/DELETE` trigger + `RAISE EXCEPTION`(阻断非法操作)
- 收回权限:`REVOKE UPDATE, DELETE ON memory_ops_log FROM app_user`
- declarative partitioning by month + 每月 freeze(老 partition 改为 READ ONLY)

**思考方向**:DB 层强制 vs 应用层强制,**正确性、灵活性、可观测性、迁移成本** 怎么权衡?面试官追问"为啥 MVP 不加 trigger" 你怎么答(线索:trigger 让 schema migration 变难;调试时 trigger 错误信息丑)。

#### Q2:`before_value` / `after_value` 都是 TEXT —— 存全文 vs 存 diff 各自取舍?

举个具体例子:`preferences` core block 改一句话,2000 字符里改了 30 字。
- 存全文:before 2000 字 + after 2000 字 = 4KB per row
- 存 unified diff:50 字符
- 存 JSON Patch(RFC 6902):80 字符

**思考方向**:磁盘占用 / 审计可读性 / 重建 "v1 → v2 → v3" 历史的难度 / Sleep 读 ops_log 时 LLM 看哪种格式更准。

#### Q3:一年攒到几十万行 ops_log,怎么演进?

候选:
- 分表(按月) → 老表 archive 到 S3
- PG declarative partitioning(按 ts 月分区)+ 老 partition `DETACH` 到 cold storage
- 直接全 INSERT,定期 `VACUUM FULL` + 压缩
- 异步流入 ClickHouse / Loki 做长期分析

**思考方向**:每个方案的 query / write 性能影响 / 运维复杂度 / MVP 到生产化的最小改动路径。

---

## §4.4 · Staging 表 + Atomic Swap

> Letta paper 的核心机制之一。**两个 staging 表 + 三对 RENAME** 解决"Sleep 改了一半数据被 Awake 读到"的问题。这是项目里**最值得讲的并发设计**。

### 整体流程

```
Sleep cycle 开始
  │
  ▼
[snapshot_to_staging]              (sleep/staging.py:38-58)
  ├─ DROP TABLE IF EXISTS core_blocks_staging CASCADE
  ├─ CREATE TABLE core_blocks_staging (LIKE core_blocks INCLUDING ALL)
  ├─ INSERT INTO core_blocks_staging SELECT * FROM core_blocks
  ├─ (重复 for archival_facts)
  ├─ COMMIT
  └─ 返回 snapshot_ts(给 atomic_swap 用)
  │
  ▼
[Sleep 8 phase 跑]                  (sleep/agent.py)
  │ 全程只写 *_staging,主表不动
  │ 每个 apply_xxx 各自 COMMIT(不是整 cycle 一个事务)
  │ Awake 此时还能正常服务,读写主表
  ▼
[atomic_swap]                       (sleep/staging.py:61-92)
  ├─ Step a: 把 cycle 期间主表新增的 archival 抓到 staging
  │     INSERT INTO archival_facts_staging
  │     SELECT * FROM archival_facts WHERE created_at > :snapshot_ts
  │     ON CONFLICT (id) DO NOTHING
  ├─ Step b: 三对 RENAME(per table,via tmp suffix)
  │     ALTER TABLE core_blocks       RENAME TO core_blocks_tmp_swap
  │     ALTER TABLE core_blocks_staging RENAME TO core_blocks
  │     ALTER TABLE core_blocks_tmp_swap RENAME TO core_blocks_staging
  │     (重复 for archival_facts)
  ├─ Step c: TRUNCATE *_staging(此时是原主表内容,清空)
  └─ COMMIT(以上全部一个 transaction)
  │
  ▼
[cleanup_staging](cycle 失败时也会跑)
  └─ DROP TABLE IF EXISTS *_staging CASCADE
```

### snapshot 实现细节

`sleep/staging.py:38-58`:
```python
async def snapshot_to_staging(session: AsyncSession) -> datetime:
    snapshot_ts = datetime.utcnow()
    for tbl in ("core_blocks", "archival_facts"):
        staging = f"{tbl}_staging"
        await session.execute(text(f"DROP TABLE IF EXISTS {staging} CASCADE"))
        await session.execute(text(f"CREATE TABLE {staging} (LIKE {tbl} INCLUDING ALL)"))
        await session.execute(text(f"INSERT INTO {staging} SELECT * FROM {tbl}"))
    await session.commit()
    return snapshot_ts
```

#### `LIKE ... INCLUDING ALL` 是啥?

PG 的 DDL 写法,等价于把 `INCLUDING DEFAULTS + CONSTRAINTS + IDENTITY + INDEXES + STATISTICS + ...` 全部打开。**一行 = 把表结构 / 索引 / 约束全复制**。比手写 DDL 干净也不会漏。

#### `snapshot_ts` 为啥用 `datetime.utcnow()` 不用 `now()`?

注意 ts 是 **Python 端取的时间**,不是 DB 端 `SELECT now()`。两者差几个毫秒:
- Python 端取 ts → snapshot 期间用户可能又写了几条 archival
- DB 端 `now()` → snapshot 完才取 ts,可能漏掉同毫秒的新写入

→ **Python 端 ts 保守一点(取早一点)**,atomic_swap 的 step a `WHERE created_at > snapshot_ts` 宁可重复抓一行(ON CONFLICT 兜底),也别漏。

### atomic_swap 实现细节

`sleep/staging.py:61-92`:

#### Step a:抓 cycle 期间主表新插入的 archival

```sql
INSERT INTO archival_facts_staging
    SELECT * FROM archival_facts
    WHERE created_at > :snapshot_ts
ON CONFLICT (id) DO NOTHING
```

→ **关键:解决了 Awake 在 cycle 期间写新 fact 的问题**。这些新 fact Sleep 没看见,但 swap 前要拷到 staging,**否则 swap 后这些行就丢了**(因为 staging 变主表)。

`ON CONFLICT DO NOTHING` 防止 id 冲突(理论上 staging 是 cycle 开始时拷的,主表新增的 id 一定大于 staging 已有的,但保险起见加)。

**这个机制覆盖不到的 case**(代码注释明说):
- Awake 期间**UPDATE** 了某行(如 `mark_archival_used` 改 `use_count`),Sleep 也 UPDATE 了同行 → **Sleep 的版本覆盖 Awake 的**
- MVP 接受这个 trade-off,因为冲突罕见(Sleep 改少数 row,Awake 改多数 row,交集小)

#### Step b:三对 RENAME(per table)

```sql
ALTER TABLE core_blocks       RENAME TO core_blocks_tmp_swap;
ALTER TABLE core_blocks_staging RENAME TO core_blocks;
ALTER TABLE core_blocks_tmp_swap RENAME TO core_blocks_staging;
```

为啥要**三对**不是两对?

```
直觉(两对):  core_blocks → 临时名 → core_blocks_staging 名字
              core_blocks_staging → core_blocks 名字
              ❌ 中间有一刻 core_blocks 名字不存在
              ❌ Awake 此时 SELECT 报 "relation does not exist"
```

正确做法(三对):
```
core_blocks       → core_blocks_tmp_swap   (主表暂改名)
core_blocks_staging → core_blocks          (staging 升主表)
core_blocks_tmp_swap → core_blocks_staging (原主表降 staging)
```

**全程 `core_blocks` 这个名字至少有一张表占着**(只是内容不同),Awake 读取不会报 "relation does not exist"。

#### Step c:TRUNCATE 现在的 staging(原主表内容)

swap 完原主表内容跑到了 staging 名下,**已经过期 + 没用**,直接 TRUNCATE 释放空间。下次 cycle 重新 snapshot 时 DROP + CREATE 会清掉(为啥不直接 DROP?TRUNCATE 比 DROP 快,且保留 schema)。

#### 全部在一个 transaction 里

```python
await session.execute(...)  # step a
await session.execute(...)  # step b × 6 次 RENAME
await session.execute(...)  # step c × 2 次 TRUNCATE
await session.commit()      # 一次提交
```

→ **要么全成功(Awake 看到新主表),要么全回滚(Awake 继续看老主表)**。中间不会出现"半新半旧"。

### RENAME 的锁行为

**关键真相**:`ALTER TABLE ... RENAME TO ...` 在 PG 里要拿 **`ACCESS EXCLUSIVE LOCK`**——最高级锁,**阻塞所有其他操作**(包括 SELECT)。

→ **swap 瞬间 Awake 的 SELECT 会被短暂阻塞**(几十毫秒到秒级,取决于现有 query 排空)。

这是个**真实的产品风险**——不是 free lunch:

| Mitigation | 做法 | 取舍 |
|---|---|---|
| swap 在 idle 时段 | 我们 cycle 本来就 idle 触发,**自然 mitigation** | 全部 cycle 都在 idle,自然冷期 |
| `SET lock_timeout=...` | swap 拿不到锁 N 秒就放弃 | swap 失败 cycle 浪费 |
| logical view 替代物理 RENAME | 用 `CREATE OR REPLACE VIEW core_blocks AS SELECT * FROM core_blocks_v2` | 多一层 view 开销 |
| 接受短暂阻塞 | MVP 选这个 | 阻塞 < 100ms,Awake 用户感知不到 |

**面试加分**:**主动承认这个 trade-off + 给 3 种 mitigation**——比假装"我设计完美"加分十倍。

### cleanup_staging —— 失败 / 异常路径

`sleep/staging.py:95-99`:
```python
async def cleanup_staging(session: AsyncSession) -> None:
    for tbl in ("core_blocks", "archival_facts"):
        await session.execute(text(f"DROP TABLE IF EXISTS {tbl}_staging CASCADE"))
    await session.commit()
```

调用时机(`sleep/agent.py:248-263` node_swap):
```python
if state.get("aborted"):
    await staging.cleanup_staging(session)   # 中途 abort 清掉
    return state
if state.get("snapshot_ts") is None:
    await staging.cleanup_staging(session)   # snapshot 失败也清
    return state
await staging.atomic_swap(...)               # 正常路径
```

+ `run_sleep_cycle()` 外层 try/except 兜底:
```python
except Exception as exc:
    try:
        await staging.cleanup_staging(session)
    except Exception:
        pass
```

→ **3 道保险**确保 staging 表不会变成孤儿(占空间又下次 snapshot 又会 DROP 但占用元数据)。

### 为啥不直接用长事务?

替代方案:`BEGIN; <几十次 UPDATE>; COMMIT;` —— 不要 staging 表,所有 Sleep 写直接打主表,事务包住。

为啥不:

| 维度 | staging 方案 | 长事务方案 |
|---|---|---|
| Awake 读阻塞 | 不阻塞(读主表) | **阻塞**(`ACCESS SHARE` 等 `ROW EXCLUSIVE`,SELECT 慢) |
| Awake 写阻塞 | 不阻塞(写主表) | **阻塞** + 死锁风险 |
| MVCC 膨胀 | 不膨胀(staging 独立) | 长事务 = MVCC dead tuples 堆积,vacuum 卡 |
| 调试可见 | staging 表能 SELECT 看进度 | 事务里看不见(其他 session 看不到) |
| 中途崩了 | staging 还在,DROP 即清 | 长事务自动 rollback(好),但数据已 lock 几分钟 |
| 实现复杂度 | 中(需要 swap 逻辑) | 低(直接 UPDATE) |

→ **staging 方案唯一缺点是实现复杂**,其他维度全胜。**MVP 选 staging 是对的**。

### §4.4 · 小结

Staging + atomic swap 在解决**一个核心问题**:让 Sleep 改数据时**不阻塞 Awake**。

机制三层:
1. **snapshot** 把数据拷副本 → Sleep 在副本上随便改
2. **三对 RENAME** 原子交换 → 一瞬间切换
3. **step a 把 cycle 期间主表新增行 merge 进 staging** → 不丢

**唯一 trade-off**:swap 那一瞬间 `ACCESS EXCLUSIVE LOCK` 短暂阻塞 Awake——已知 + 可接受 + 有 mitigation 方向。

**面试加分句**:
> "staging swap 是个 read-side 永不阻塞的设计——Sleep 全程在 staging 副本上工作,Awake 读写主表不被打扰。唯一的 sync 点是 swap 瞬间的 RENAME,需要 ACCESS EXCLUSIVE LOCK。这个阻塞短(几十毫秒),且 cycle 本来就在 idle 时段触发,自然 mitigation。代价是实现复杂度比长事务高,但避免了长事务的 MVCC 膨胀和读阻塞,工程上正解。"

### §4.4 · 课后思考题(已答 + 点评)

#### Q1:整表复制 snapshot 在 100 万行场景怎么样?

**用户回答**:大数据量整表复制有严重性能问题;想"只复制要动的行",但自己质疑——sleep 决策是动态的,能一开始就确定要动哪些行吗?

**点评 —— 你那个自我质疑就是题眼**:

**对,无法预先确定**。Sleep 要先读数据 → 喂 LLM → LLM 才决定动哪些行。决策依赖数据已在手,所以"只复制要动的行"走不通(你已经自己否掉了,很好)。

那大数据量怎么破?**换思路:既然改的行少,就别复制整表,改成"内存决策 + 短事务 apply"**:

```
MVP:       复制整表 → 副本上改 → swap 整表
大数据量:  MVCC 快照读主表(不锁/不复制) → 内存里算好所有决策
          → 最后一个【短事务】只 UPDATE 那几行
```

核心洞察:**Sleep 本质是"读一大堆、想一想、改几行"**。读阶段用 PG 的 `REPEATABLE READ` 快照读(一致时间点,不锁不复制),写阶段只用短事务 apply 少数行。**根本不需要 staging 整表复制**——整表复制是 MVP 为"隔离彻底、实现简单"选的,数据量大时这权衡反转(复制 4GB 成本 >> 隔离的简单性)。

**整表复制在 100 万行的三个具体问题**:
1. **耗时**:复制 100 万行 + 重建 HNSW 索引几分钟,cycle 没开始干活就超 budget
2. **磁盘**:主表 4GB + staging 4GB 翻倍,每 cycle 一遍
3. **主表影响**:`INSERT ... SELECT * FROM main` 全表扫,拖慢主表并发读

#### Q2:swap 的 RENAME 拿 ACCESS EXCLUSIVE LOCK,撞上 Awake 慢查询会怎样?

**用户回答**:swap 拿不到锁要等;后面来的也加入等待;设锁超时时间。

**点评 —— 全对,补一个反直觉的放大效应:队头阻塞(head-of-line blocking)**:

PG 锁等待是 **FIFO 队列**。RENAME 在等前面的慢查询时排进队列。关键来了:

> 排在这个"等待中的 EXCLUSIVE"**后面**的新读请求,**即使和当前持锁的慢查询本来兼容(读读不冲突),也会被挡住**。

为啥?PG 为**防止写饥饿**(避免读源源不断插队害写永远拿不到锁),规定后来者不能越过队列里在等的排他锁。

→ 实际后果被放大:不是"swap 自己等 5 秒",而是 **"swap 等待的 5 秒里所有新读全堵在它后面"**——一个慢查询 + 一个等待的 RENAME = 雪崩式阻塞。

这正是 `lock_timeout` 的真正动机:
```sql
SET lock_timeout = '500ms';   -- 等不到就放弃 swap,把队列让出来,堵着的读立刻放行
```
**快速失败 > 无限期堵塞**。

#### Q3:cycle 期间 Awake 写主表的行,swap 时怎么不丢?(+ 字段级合并)

**用户回答**:不能接受丢信息;但没理解 step a 是什么。

**点评**:

**step a** = `atomic_swap` 的第一步(swap 前先捞回新增行):
```sql
INSERT INTO archival_facts_staging
    SELECT * FROM archival_facts WHERE created_at > :snapshot_ts
ON CONFLICT (id) DO NOTHING;   -- 然后 step b 三对 RENAME,step c truncate
```
精度细节:`snapshot_ts` 取 **Python 时间**(`datetime.utcnow()`)保守划早一点,宁可重复捞(ON CONFLICT 兜底)也别漏。

**但 step a 只覆盖 INSERT(新增整行),不管 UPDATE(老行被改)**。所以 cycle 期间 Awake 对老行的 `use_count +1` 会被 Sleep 整行覆盖丢掉。

**为什么整行覆盖会丢(带数字例子)**:

| 时刻 | 发生 | 主表 id=5 | staging id=5 |
|---|---|---|---|
| T0 snapshot | 复制 | content="A", use_count=**10** | content="A", use_count=**10** |
| T1 | Sleep 改 content | content="A", uc=10 | content="**A合并版**", uc=10 |
| T1.5 | Awake recall 命中,主表 +1 | content="A", uc=**11** | content="A合并版", uc=10 |
| T2 swap | 整行覆盖 | → 结果 content="A合并版", uc=**10** ❌ | |

→ uc 从 11 被打回 10,Awake 那次 +1 没了。**根因不是两人改同一字段**(Sleep 改 content、Awake 改 uc,是不同字段),而是 **staging 那行携带了 snapshot 时刻的过期 uc(10),整行覆盖时把过期值一起搬过去盖了主表的新值**。

**字段级合并解法**:swap 时不整行盖,**按字段分归属**:

| 字段 | 归谁 | swap 取谁 |
|---|---|---|
| content / confidence / is_deleted | Sleep(语义决策) | staging |
| use_count / last_used_at | Awake(访问统计) | 主表 |

实现 = swap 前把主表的统计字段回填进 staging:
```sql
UPDATE archival_facts_staging s
SET use_count = m.use_count, last_used_at = m.last_used_at
FROM archival_facts m
WHERE s.id = m.id;
```
→ content 取 Sleep 的,use_count 取 Awake 的,**谁也不盖谁**。这正是代码注释里 "Day 03+: row-level merge for use_count / last_used_at" 的 TODO。

**收口认知**:冲突根源是"整行覆盖这个粗暴动作",不是"抢同一字段"。**解法不是加锁,是按字段划分所有权**(语义归 Sleep,统计归 Awake)。

---

## §4.5 · 跨表设计取舍

> 单表设计能讲,**跨表的"为啥不那么连"** 更体现深度。面试官常用"你为什么不加 FK?" 这种问题钓你——答得好加分,答得差直接 senior 印象。

### 取舍 1:为啥 core 和 archival 不合一张表?

替代方案:**union schema** —— 一张 `memory_blocks` 表加个 `kind` 字段区分 core / archival。

```sql
-- 假想的 union schema
CREATE TABLE memory_blocks (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,           -- 'core' / 'archival'
    label       TEXT,                    -- 只 core 用
    content     TEXT NOT NULL,
    embedding   vector(1024),            -- 只 archival 用
    char_limit  INT,                     -- 只 core 用
    use_count   INT,                     -- 只 archival 用
    confidence  SMALLINT,                -- 只 archival 用
    ...
);
```

为啥不:

| 问题 | 解释 |
|---|---|
| **字段 50% NULL** | core 行的 embedding/use_count/confidence 都空,archival 行的 char_limit/label 都空 → 表 schema 半废 |
| **索引被拖累** | HNSW 索引要 `WHERE kind='archival'` 才用,partial index 写法丑 |
| **权限规则难写** | "Sleep 才能改 core" 变成 "Sleep 才能改 kind='core' 的行" → check 在哪都得带 kind 条件 |
| **演化方向反** | core / archival 未来会**朝不同方向演化**(core 加 char_limit 调整规则,archival 加 embedding model 切换),union 后改 schema 互相牵制 |

→ **分两张表是 Letta paper 的设计,跟我们的思路一致**。MVP 不犹豫。

### 取舍 2:为啥不加 FK `archival.core_block_label REFERENCES core_blocks(label)`?

直觉上 archival 被 promote 成 core 的某块,加个 FK 表达这层关系似乎更"正确"。

**为啥故意不加**:

1. **promote 不是关联,是决策事件** —— archival 在被 Sleep `promote` 之前,**根本不知道自己将来去哪个 core block**。`use_count` 高到阈值 + LLM 评估 → 才决定升 / 不升 / 升哪块。
2. **加 FK = 过早 commit** —— 假设 archival 创建时就要填 FK,那要么留 NULL(95%+ 都 NULL,FK 形同虚设),要么强制填一个但促狭了未来 promote 的灵活性。
3. **关系本质在 ops_log 里** —— `sleep_promote` op_type 的 ops_log 已经记录 "archival id=42 → core preferences",**这就是关系**,只是用事件流而非 FK 表达。

类比 **event sourcing vs CRUD**:CRUD 是"现在状态",event sourcing 是"如何到达现在状态"。FK 偏 CRUD 思维,**memory 系统本质是 event sourcing**(每次 promote / consolidate / demote 都是事件)。

**通用经验**:**FK 不是越多越好,过早 commit 的关系比无关系更坏**。其他例子:
- 订单 - 产品快照(加 FK,产品下架订单变孤儿)
- 用户 - 历史地址(加 FK,用户改地址历史订单的地址跟着变)
- 事件 - 实体(加 FK,事件不再 immutable)

### 取舍 3:关系 + 向量同库 vs 分两个 DB?

替代方案:**Mysql / PG 存关系数据,Milvus / Pinecone 存向量** —— 业界常见拆法。

为啥我们合一个 PG:

| 维度 | 合 PG | 分双库 |
|---|---|---|
| 事务 | **跨表事务原生**(fact + ops_log 同 transaction) | 跨库事务 = 噩梦(2PC 或最终一致性) |
| join | 向量结果 join 关系数据原生 SQL | 业务代码两次 query 手动 join |
| 运维 | 一套 backup / monitor | 两套 |
| 性能上限 | pgvector 到亿级 vector 性能下降 | Milvus 这种专用 DB 上限高 |
| 复杂度 | 低 | 高(数据同步、一致性) |

**关键判断**:**我们项目永远到不了"亿级 vector"** → pgvector + PG 是最优解。**面试官说"为啥不用 Milvus 性能更好" → 答"我永远没那个数量级,过度设计是反 senior"**。

### 取舍 4:为啥不加 `user_id`(MVP 单用户写死)

`mcp_server.py` / `awake/agent.py` / 整个 codebase **找不到 `user_id` 字段** —— 写死单用户。

**为啥故意这么做**:
- 加 `user_id` 涉及到 **3 张表都要加列 + 全部 query 加 WHERE user_id = ? + 索引复合**
- MVP 验证的是**架构正确性 + Letta 思路落地**,不是 multi-tenant
- **过早 multi-tenant 化** = 加一堆没用的 column,真要 multi-tenant 时反而要重做(因为 single-user 假设藏在很多地方)

未来真要 multi-tenant 时有两条路:

**方案 A:3 张表都加 `user_id` 列**
- pros:1 个 DB 1 套 schema,运维简单
- cons:**所有 query 都得带 user_id**,忘一处 = 数据泄漏;HNSW 索引要 `(user_id, embedding)` 复合,性能影响待评估;ops_log 要双索引 `(user_id, ts)` + `(user_id, actor, ts)`

**方案 B:每个 user 独立 PG schema**(`CREATE SCHEMA user_xxx` + `SET search_path TO user_xxx`)
- pros:**结构上隔离**,query 不可能跨 user;每个 user 独立 HNSW 索引;backup / restore 独立
- cons:1000 user = 1000 schema,DDL migration 痛苦;PG 元数据爆炸

**实际**:看 user 量分档:
- < 100 user:方案 B(隔离干净)
- 100-10k user:方案 A(规模化)
- > 10k user:**多实例分片**(每个 PG 实例承担 N 个 user 的 schema 集合)

### 取舍 5:为啥 5 个 core block 不允许动态增减

`core_blocks` 表 `INSERT ON CONFLICT DO NOTHING` 把 5 个 label 写死。**没有 API 允许新增第 6 个 / 删除某个**。

为啥:
- core 是**用户画像的固定维度**,不是 tag —— 维度数变了所有 Sleep prompt 都要重写
- 5 个 label(background/preferences/habits/skills/lessons_learned)是 Letta paper 推荐的最小 + 正交集
- 如果某天发现需要第 6 个(比如 `relationships`),那是个**架构决策**,不是运行时操作

→ **schema 上没限制(label 是 TEXT 不是 ENUM),但应用层不暴露增减 API**。等需要时再加。

### §4.5 · 小结

5 个取舍背后是同一个原则:**避免过早 commit**。

| 取舍 | 为啥不做"看起来更对"的事 |
|---|---|
| 合一张表 | 字段差异太大,union 后管理成本 > 分表成本 |
| 加 FK | promote 是决策事件不是关联,FK 过早 commit |
| 双库 | 跨库事务噩梦,而且我们没那个 scale |
| 加 user_id | 不是 multi-tenant 业务,加了反而难真 multi-tenant 化 |
| 动态 core label | core 是架构维度不是运行时数据 |

**面试加分句**:
> "数据模型设计的关键不是'还能加什么字段',是'哪些字段不加'。我项目里故意不加 FK、不加 user_id、不动态增 core label,都是为了**避免过早 commit**——MVP 阶段把决策延后,等真有需求再加。这比一开始 over-design 然后改起来重不知道好多少。"

### §4.5 · 课后思考题

#### Q1:给 archival 加 FK `core_block_label REFERENCES core_blocks(label)` 看起来更"正确"——但我有意不加。为啥?

提示:
- archival 在被 Sleep `promote` 之前,**根本不知道自己将来去哪个 core block**
- 加 FK = 过早 commit = 大部分 archival 永远 NULL(96% 的 archival 不会被 promote)
- promote 是个**决策**不是**关联**——决策不该用 schema 强约束

**思考方向**:**"FK 不是越多越好"** 这个反直觉的工程经验,你能举出别的反例吗?(线索:订单 - 产品快照,如果加 FK 产品下架订单就坏;事件源 - 实体,FK 让事件追溯变难)

#### Q2:未来 multi-tenant 怎么改造?

两种方案:

**方案 A:3 张表都加 `user_id` 列**
- pros:1 个 DB 1 套 schema,运维简单
- cons:**所有 query 都得带 user_id**,忘一处 = 数据泄漏;HNSW 索引要 `(user_id, embedding)` 复合

**方案 B:每个 user 独立 PG schema**(`CREATE SCHEMA user_xxx` + `SET search_path TO user_xxx`)
- pros:**结构上隔离**,query 不可能跨 user;每个 user 独立 HNSW 索引
- cons:1000 user = 1000 schema,DDL migration 痛苦;PG 元数据爆炸

**思考方向**:你倾向哪个?**为啥**?面试官追问"如果 user 量 10/100/10000 各怎么选" 你能分档答吗?

#### Q3:一年攒到 50 万行 archival,query 性能会先在哪栽?

候选热点:
- HNSW 索引 build 时间(rebuild 一次几小时?)
- partial index `WHERE is_deleted=FALSE` 的索引倾斜
- `use_count` UPDATE 的写热点(每次 recall 都 UPDATE 同几行)
- staging snapshot 复制 50 万行的耗时(几分钟?)
- pgvector 1024 维向量内存占用(50 万 × 4KB = 2GB)

**思考方向**:**先栽的是哪个**?你能写出**性能测试方案**吗?(不需要真跑,**能描述出测什么** = 体现 senior 思维)

---

## §4.6 · §4 章末小结

> 把 §4.1-§4.5 收敛成 **3 个设计原则**——这是数据模型该背的总纲。

### 三个设计原则

#### ① 约束驱动(constraint-driven)

通过 schema 约束防 anti-pattern,**比"靠开发者自觉"稳得多**。

| 字段 / 索引 / 取舍 | 在约束什么 |
|---|---|
| `core_blocks.label PRIMARY KEY` 固定 5 个 | 防止 core 维度膨胀 |
| `core_blocks.char_limit DEFAULT 2000` | 防止 core 长成大杂烩 |
| `core_blocks.last_writer` 列 | DB 层兜底应用层 invariant |
| `archival_facts.confidence SMALLINT 1/2/3` | 防止 LLM 输出 0.7 这种没意义的小数 |
| `archival_facts.is_deleted BOOLEAN` + partial index | 防止软删失去性能 |

#### ② 信号驱动(signal-driven)

数据**主动给 Sleep 喂信号**,不是 Sleep 被动扫表。

| 字段 | 给谁的信号 |
|---|---|
| `archival_facts.use_count` | Awake 命中后 +1 → Sleep promote 候选信号 |
| `archival_facts.last_used_at` | Awake 命中后 = now() → Sleep demote 反向信号 |
| `archival_facts.confidence` | Awake 写入时定 1/2/3 → Sleep 阈值过滤信号 |
| `core_blocks.version` | Sleep 每次写 +1 → 跨 cycle 比对信号 |
| `memory_ops_log.reason` | 每次 mutation 留 LLM 理由 → Sleep reflect 回溯信号 |

→ **核心思想**:read 时悄悄写信号,write 时显式留理由,Sleep 不用问任何人就有充分信息做决策。

#### ③ 容错驱动(fault-tolerance-driven)

故意做弱依赖 / 软隔离,让局部失败不波及全局。

| 设计 | 容什么错 |
|---|---|
| `archival_facts.embedding` nullable | 容许 embedding API 失败时 fact 仍可入库(schema 留接口,代码 MVP 暂未启用) |
| `archival_facts.is_deleted` 软删 | 容许 forget 决策错了能恢复 |
| `memory_ops_log` append-only | 容许任何写入后都能溯源 |
| staging 表 | 容许 Sleep 跑错不影响 Awake |
| Sleep `try/except + cleanup_staging` | 容许 cycle 中途崩 |
| `nullable target_kind` in ops_log | 容许 reflect 这种没明确 target 的操作 |

### 三原则在一张表上

|  | 约束驱动 | 信号驱动 | 容错驱动 |
|---|---|---|---|
| `core_blocks` | char_limit / last_writer / 固定 label | version | (Sleep 经 staging 写) |
| `archival_facts` | confidence 离散 / is_deleted bool | use_count / last_used_at | embedding nullable |
| `memory_ops_log` | (无 trigger 是 MVP 取舍) | reason 字段 | append-only |
| 索引 | partial index | - | - |
| 跨表取舍 | 不加 FK / 不 user_id | - | 分表防字段污染 |
| Staging | - | - | 整个 staging 机制就是容错 |

### 30 秒口径

> "数据模型 3 张主表 + 2 staging。core_blocks 是 5 张固定便签强约束,archival_facts 是无限自由 fact 带向量,memory_ops_log 是 append-only 审计。设计有 3 条原则:**约束驱动**——char_limit、固定 label、离散 confidence 都在防 anti-pattern;**信号驱动**——use_count、last_used、reason 让 Sleep 拿到所有决策信息,read 时悄悄写,write 时强制留理由;**容错驱动**——embedding nullable、软删、staging 表都允许局部失败不波及全局。3 个原则,每个 schema 决策能映射到其中之一。"

### §4.6 · 课后思考题

#### Q1:你能在不看 schema.sql 的情况下,**手画出 3 张主表 + 2 张 staging 表的字段**吗?

回家不看代码,在纸上画。画完跟代码对照,差哪几个字段 = **下次重点复习**。

#### Q2:如果一句话讲完整个数据模型设计,你怎么讲?

提示骨架:**"3 主表对应 core / archival / 审计,2 staging 表给 Sleep 工作区。core 是 5 张固定便签强约束,archival 是无限自由 fact 带向量,ops_log 是 append-only 审计。设计上三个原则:(1) 约束驱动—— core 的字符上限和 version;(2) 信号驱动—— archival 的 use_count 和 last_used 喂给 Sleep;(3) 容错驱动—— embedding nullable 容许 defer-write。"**

→ 你自己写一版,下次跟我这版对比。

---

# §5 · 端到端流程 trace

> 把项目从入口到落库**完整跑一遍**——讲完这章你应该能在白板上画出 remember 链路和 sleep cycle 链路的每一步,包括**谁调谁、几次 LLM 调用、几次 DB round-trip、错误怎么传播**。

---

## §5.1 · 一次 `remember` 完整跑(秒级)

场景:用户在 Claude Code 里说"记一下我喜欢 4 空格"。

### 时序图

```
Claude Code (LLM A: Claude Sonnet)
    │ 用户说"记一下我喜欢 4 空格"
    │ LLM A 决定调 MCP tool
    ▼
[MCP HTTP POST]  localhost:8000/mcp
    body: { tool: "remember", args: { content: "...", tags: ["preference"], confidence: 3 } }
    │
    ▼
mcp_server.py: @mcp.tool() remember(...)
    │ 1. mark_awake_activity()        ← scheduler.py module 变量更新
    │ 2. 包装 command 字符串
    │    "remember this fact about the user: \n  content: ... \n  tags: preference \n  confidence: 3"
    │ 3. 调 run_awake(command)
    ▼
awake/agent.py: run_awake(command)
    │ - get_awake_agent() (lazy singleton)
    │ - agent.ainvoke({"messages": [("user", command)]})
    ▼
LangGraph create_react_agent (LLM B: DeepSeek)
    │
    │ ┌─ ReAct Step 1 ────────────────────────────────────────┐
    │ │ [Reason] LLM B 看 SYSTEM_PROMPT + command + 5 tools │
    │ │ → 决定调 search_archival(query=content)             │
    │ │ [Act]  search_archival 工具被 LangGraph 调用         │
    │ └─────────────────────────────────────────────────────┘
    │     │
    │     ▼
    │ awake/tools.py: search_archival(query, limit=5)
    │     │ - session_factory() 拿 async session
    │     │ - semantic_search_archival(session, query, limit)
    │     │   ├─ embed_text(query) ──→ 阿里通义 API call #1
    │     │   ├─ SELECT ... embedding <=> vec ORDER BY distance LIMIT 5
    │     │   └─ 返回 [] (假设没找到重复)
    │     │ - mark_archival_used([]) (空 list 无操作)
    │     └─ 返回 {"results": []}
    │     │
    │     ▼
    │ [Observe] LLM B context 收到 "{"results": []}"
    │
    │ ┌─ ReAct Step 2 ────────────────────────────────────────┐
    │ │ [Reason] LLM B 看到没重复,决定 insert                  │
    │ │ → 决定调 insert_archival_fact(content=..., tags=..., │
    │ │                              confidence=3, reason=…)  │
    │ │ [Act]  insert_archival_fact 工具被调用                │
    │ └─────────────────────────────────────────────────────┘
    │     │
    │     ▼
    │ awake/tools.py: insert_archival_fact(...)
    │     │ - insert_archival(session, ..., actor='awake_agent', reason=...)
    │     │   ├─ embed_text(content) ──→ 阿里通义 API call #2
    │     │   ├─ session.add(ArchivalFact(..., embedding=vec))
    │     │   ├─ session.flush()        # 拿 fact.id (自增)
    │     │   ├─ session.add(MemoryOpsLog(op_type='remember', actor='awake_agent', ...))
    │     │   └─ session.commit()       # 一次 commit:fact + ops_log 原子
    │     └─ 返回 {"status": "ok", "fact_id": 123, "content": "..."}
    │     │
    │     ▼
    │ [Observe] LLM B context 收到 "{"status": "ok", ...}"
    │
    │ ┌─ ReAct Step 3 ────────────────────────────────────────┐
    │ │ [Reason] LLM B 决定任务完成,生成 final answer        │
    │ │ → "已记住, fact_id=123: '用户喜欢 4 空格'"             │
    │ └─────────────────────────────────────────────────────┘
    ▼
返回 dict {"final_message": "...", "step_count": 6}
    │
    ▼
mcp_server.py: 返回 MCP response
    │
    ▼
HTTP 200 → Claude Code (LLM A) 收到
    │ LLM A 决定告诉用户"已记住"
    ▼
用户终端显示"已记住"
```

### 调用次数清算

| 类型 | 次数 | 在哪 |
|---|---|---|
| **LLM B (DeepSeek)** | **3 次** | ReAct Step 1/2/3,每次一次 chat API call |
| **Embedding (阿里通义)** | **2 次**(可降到 1) | query 查重 + content 入库;但 remember 场景下 **query=content 是同一文本**,算了两遍 → 可 cache 复用(见下方讨论补录,优化点) |
| **DB SELECT** | 1 次 | `semantic_search_archival` 那个 ORDER BY vector |
| **DB INSERT** | 2 次(同 transaction) | 1 次 `ArchivalFact`,1 次 `MemoryOpsLog` |
| **DB UPDATE** | 0 次 | (假设 search 返回空,`mark_archival_used` 不跑) |
| **DB COMMIT** | 1 次 | (fact + ops_log 在同一 transaction) |
| **HTTP round-trip(MCP)** | 1 次 | Claude Code ↔ Mneme |

### 延时分布(估算)

| 步骤 | 耗时 |
|---|---|
| MCP HTTP round-trip | ~5 ms |
| LLM B Step 1 决策 | ~800-1500 ms(DeepSeek API) |
| embed_text(query) | ~200 ms(阿里通义 API) |
| DB SELECT(HNSW) | ~5 ms |
| LLM B Step 2 决策 | ~800-1500 ms |
| embed_text(content) | ~200 ms |
| DB INSERT × 2 + COMMIT | ~10 ms |
| LLM B Step 3 finalize | ~500-1000 ms |
| **总计** | **~2.5 - 4.5 秒** |

→ 瓶颈在 **LLM 调用(占 95%+)**,DB / embedding 都是 ms 级。

### Token 成本估算

| 步骤 | Input | Output | 备注 |
|---|---|---|---|
| LLM B Step 1 | ~2000 tok(SYSTEM_PROMPT + tools schema + command) | ~100 tok(tool call JSON) | |
| LLM B Step 2 | ~2200 tok(+ observation) | ~150 tok(insert call) | |
| LLM B Step 3 | ~2400 tok | ~80 tok(final summary) | |
| **总计** | **~6600 input** | **~330 output** | |

DeepSeek-chat 定价(2026 估算):input ~$0.14/M tok, output ~$0.28/M tok
- input 成本:6600 × $0.14e-6 = **$0.001**
- output 成本:330 × $0.28e-6 = **$0.0001**
- **一次 remember ≈ $0.0011**

对比 GPT-4o(假设)同样调用 ≈ **$0.025**,**贵 22 倍**——这就是 §2.4 选 DeepSeek 的实证。

### 错误怎么传播

| 错点 | 行为 |
|---|---|
| MCP HTTP 失败 | Claude Code 重试 / 报错 |
| embed_text 失败 | `insert_archival` 整个抛异常 → MCP 返回 error → LLM A 看到 |
| DB INSERT 失败(违反约束) | session.commit 抛异常 → 回滚 → fact + ops_log 都没写 |
| LLM B Step 决策乱来 | LangGraph max_iterations 兜底(默认 25)→ 强制结束 |

### 简化版(去重路径)

如果 `search_archival` 找到 distance < 0.1 的重复:
1. Step 1:search → 找到 dup
2. Step 2:LLM B 决定不 insert,直接 final answer "已存在重复"
3. **只 2 个 LLM call + 1 个 embedding call + 1 个 DB SELECT**

→ **去重路径明显省钱**,这是 `SYSTEM_PROMPT` 里强制"先 search 后 insert" 的理由。

### §5.1 · 讨论补录(修正 + 优化点)

#### 1. query 和 content 分别是什么(分场景)

| | content | query |
|---|---|---|
| **remember 场景** | 要**记住的 fact** 本身("我喜欢 4 空格"),存进 `archival_facts.content` + 算 embedding | 查重用的搜索词,**拿 content 当 query**(`search_archival(query=content)`)→ **二者同一文本** |
| **recall 场景** | 不存在(recall 只读不写) | 用户的**检索问题**("我的代码风格偏好是啥")|

一句话:**content = 要记的内容,query = 要搜的问题**。remember 里二者恰好同文本,recall 里只有 query 没有 content。

#### 2. 【修正 + 优化点】remember 的两次 embedding 是同一文本,可复用

前面"调用次数"说 2 次 embedding 算"不同文本"**不准确**:remember 里查重(query)和入库(content)是**同一段文本**,各算一次 = **浪费一次 embedding API**。

→ **优化点**:算一次,查重和插入复用同一向量。MVP 没做,是明显的省 token 点。
> 面试话术:"remember 链路里查重和插入对同一文本各算了一次 embedding,可以 cache 复用——MVP 没做。"

#### 3. 【优化点】写异步、读同步

**现状**:MCP 的 `remember` 是 `return await run_awake(cmd)`,**同步阻塞** 2.5-4.5 秒才返回。MCP 协议本就是请求-响应,Claude Code 调了得等返回。是否拖慢体验取决于 Claude Code **何时**调(答完用户之后调 → 无感;边答边记 → 卡顿),而调用时机**不是我们能控制的**。

**优化方向 —— 按工具语义区分同步/异步**:

| 工具类型 | 同步/异步 | 理由 |
|---|---|---|
| **`remember` / `forget`**(写) | **可异步 fire-and-forget** | 用户不等结果,立刻返回"已收到",后台跑 Awake |
| **`recall` / `list_memory`**(读) | **必须同步** | Claude Code 要拿结果才能回答用户 |

异步的代价:写类工具异步后**拿不到 fact_id、拿不到同步去重结果、失败用户不知道**。所以"写异步"成立的前提是 **写操作不需要同步返回信息**。

> 面试话术:"MVP 的 remember 同步会阻塞 tool 调用 2.5-4.5 秒。优化是把写类工具(remember/forget)做成 fire-and-forget 立刻返回、后台处理,读类工具(recall)保持同步因为要拿结果回答用户。代价是写类失去同步去重和 fact_id 返回。这是按工具语义区分同步/异步的设计。"

---

## §5.2 · 一次 Sleep Cycle 完整跑(分钟级)

场景:Awake 30 分钟无活动,APScheduler `_idle_tick()` 触发。

### 时序图

```
APScheduler (每 60s 跑 _idle_tick)
    │ _idle_seconds() >= 1800 (默认 30 min)
    │ _cycle_running == False
    ▼
_try_run_cycle("idle")
    │ _cycle_running = True
    │
    ▼
sleep/agent.py: run_sleep_cycle()
    │ - deadline = monotonic() + 300s (5 min budget)
    │ - init_state = {"deadline_ts": deadline, "aborted": False, ...}
    │ - graph = get_sleep_graph()  (lazy singleton)
    │ - await graph.ainvoke(init_state)
    ▼

┌─────────────────────────────────────────────────────────────┐
│  LangGraph StateGraph 跑 8 节点                              │
└─────────────────────────────────────────────────────────────┘

[① node_snapshot]
    │ check budget: deadline 还有 297s,OK
    │ Session = get_sessionmaker()
    │ await snapshot_to_staging(session)
    │   ├─ DROP TABLE IF EXISTS core_blocks_staging CASCADE
    │   ├─ CREATE TABLE core_blocks_staging (LIKE core_blocks INCLUDING ALL)
    │   ├─ INSERT INTO core_blocks_staging SELECT * FROM core_blocks
    │   ├─ (同 for archival_facts)
    │   └─ COMMIT, 返回 snapshot_ts
    │ state["snapshot_ts"] = snapshot_ts
    │ 耗时: 100-500 ms(取决于 archival 行数)
    ▼

[② node_plan]
    │ summary = await tools.summarize_state(session, _last_cycle_ts)
    │   ├─ SELECT core_blocks
    │   ├─ COUNT archival WHERE is_deleted=FALSE
    │   ├─ COUNT new archival since last_cycle_ts
    │   ├─ COUNT stale archival
    │   └─ EXISTS high_freq archival
    │ rendered = PLAN_PROMPT.format(state_summary=..., min_archival=...)
    │ decision = await _llm_json(rendered)  ──→ DeepSeek API call #1
    │   返回 {"phases": ["consolidate", "promote", "reflect"], "reason": "..."}
    │ state["plan"] = phases
    │ 耗时: ~1-2 秒(LLM)
    ▼

[③ node_consolidate]  (if "consolidate" in plan)
    │ clusters = await tools.find_consolidation_clusters(session)
    │   ├─ SELECT id, content, embedding FROM archival_facts_staging WHERE embedding IS NOT NULL
    │   ├─ 贪心聚类(O(N²) MVP,N<1000 OK)
    │   │   for each row_i not visited:
    │   │     SELECT id, content, embedding <=> row_i.embedding AS dist
    │   │     FROM staging WHERE id != row_i.id ORDER BY dist LIMIT 5
    │   │     for c in cands: if dist < 0.15: cluster.append(c)
    │   └─ 返回 [[fact_a, fact_b, fact_c], ...] (top 10 cluster)
    │ if clusters:
    │   rendered = CONSOLIDATE_PROMPT.format(clusters_json=...)
    │   decision = await _llm_json(rendered)  ──→ DeepSeek API call #2
    │     返回 {"actions": [{"decision":"MERGE","kept_id":...,"discarded_ids":[...],"merged_content":...,...}]}
    │   await tools.apply_consolidation(session, actions)
    │     ├─ for each MERGE action:
    │     │   UPDATE archival_facts_staging SET content=:merged WHERE id=:kept
    │     │   UPDATE archival_facts_staging SET is_deleted=TRUE WHERE id = ANY(:discarded)
    │     │   INSERT INTO memory_ops_log (op_type='sleep_consolidate', ...)
    │     └─ COMMIT
    │ state["consolidate_actions"] = actions
    │ 耗时: ~3-10 秒(LLM + cluster query)
    ▼

[④ node_promote]  (if "promote" in plan)
    │ candidates = await tools.get_promote_candidates(session)
    │   SELECT * FROM archival_facts_staging
    │   WHERE use_count >= 5 AND confidence >= 3
    │   ORDER BY use_count DESC LIMIT 20
    │ if candidates:
    │   summary = await tools.summarize_state(session, None)  # 拿当前 core 内容
    │   rendered = PROMOTE_PROMPT.format(core_blocks_json=..., candidates_json=...)
    │   decision = await _llm_json(rendered)  ──→ DeepSeek API call #3
    │     返回 {"actions": [{"decision":"PROMOTE","fact_id":...,"target_block":"preferences","new_block_value":"...","reason":...}, ...]}
    │   await tools.apply_promotions(session, actions)
    │     ├─ for each PROMOTE:
    │     │   SELECT value FROM core_blocks_staging WHERE label=:target (留 before)
    │     │   UPDATE core_blocks_staging SET value=:v, version=version+1, last_writer='sleep_agent' WHERE label=:target
    │     │   INSERT INTO memory_ops_log (op_type='sleep_promote', ...)
    │     └─ COMMIT
    │ state["promote_actions"] = actions
    │ 耗时: ~2-5 秒
    ▼

[⑤ node_demote]
    │ stale = get_stale_candidates(session)
    │   SELECT * FROM archival_facts_staging
    │   WHERE confidence = 1 AND (last_used_at IS NULL OR last_used_at < now() - 90 days)
    │   ORDER BY created_at ASC LIMIT 50
    │ if stale:
    │   rendered = DEMOTE_PROMPT.format(stale_json=...)
    │   decision = await _llm_json(rendered)  ──→ DeepSeek API call #4
    │     返回 {"actions": [{"fact_id":..., "decision":"FORGET", "reason":...}, ...]}
    │   await tools.apply_demotions(session, actions)
    │     ├─ UPDATE archival_facts_staging SET is_deleted=TRUE WHERE id=:i
    │     ├─ INSERT INTO memory_ops_log (op_type='sleep_demote', ...)
    │     └─ COMMIT
    │ 耗时: ~2-5 秒
    ▼

[⑥ node_resolve]
    │ summary = await tools.summarize_state(...)
    │ recent = SELECT op_type, actor, target_id, reason, ts FROM memory_ops_log ORDER BY ts DESC LIMIT 20
    │ rendered = RESOLVE_PROMPT.format(core_blocks_json=..., recent_ops_json=...)
    │ decision = await _llm_json(rendered)  ──→ DeepSeek API call #5
    │   返回 {"contradictions": [{"blocks_involved":[...], "fix_block":"...", "new_block_value":"...", ...}]} 或 {"contradictions":[]}
    │ await tools.apply_resolutions(session, contradictions)
    │   ├─ UPDATE core_blocks_staging SET value=:v WHERE label=:fix_block
    │   ├─ INSERT INTO memory_ops_log (op_type='sleep_consolidate', ...)  ← NOTE: 用了 consolidate 不是 resolve(MVP wart)
    │   └─ COMMIT
    │ 耗时: ~2-5 秒
    ▼

[⑦ node_reflect]
    │ summary = await tools.summarize_state(...)
    │ highlights = SELECT id, content, confidence, use_count FROM archival_facts_staging WHERE is_deleted=FALSE ORDER BY confidence DESC, use_count DESC LIMIT 5
    │ rendered = REFLECT_PROMPT.format(core_blocks_json=..., archival_highlights_json=...)
    │ llm = get_chat_llm(temperature=0.3)  ← 唯一不用 0.0 的 phase
    │ resp = await llm.ainvoke([HumanMessage(content=rendered)])  ──→ DeepSeek API call #6
    │   返回 plain text "User is a Java backend intern at Thunderbit..."
    │ await tools.log_reflection(session, reflection_text)
    │   ├─ INSERT INTO memory_ops_log (op_type='sleep_reflect', target_kind=NULL, after_value=text, ...)
    │   └─ COMMIT
    │ 耗时: ~2-4 秒
    ▼

[⑧ node_swap]
    │ if aborted: cleanup_staging + return
    │ if snapshot_ts is None: cleanup_staging + return
    │ await staging.atomic_swap(session, snapshot_ts)
    │   ├─ INSERT INTO archival_facts_staging SELECT * FROM archival_facts
    │   │     WHERE created_at > :snapshot_ts ON CONFLICT (id) DO NOTHING
    │   ├─ ALTER TABLE core_blocks RENAME TO core_blocks_tmp_swap
    │   │   ALTER TABLE core_blocks_staging RENAME TO core_blocks
    │   │   ALTER TABLE core_blocks_tmp_swap RENAME TO core_blocks_staging
    │   ├─ (同 for archival_facts)
    │   ├─ TRUNCATE core_blocks_staging
    │   ├─ TRUNCATE archival_facts_staging
    │   └─ COMMIT
    │ 耗时: ~50-200 ms
    ▼

[END]
    │ _last_cycle_ts = datetime.utcnow()
    │ 返回 result dict
    ▼

scheduler.py: _cycle_running = False
              mark_awake_activity() (避免立即 re-trigger)
```

### 调用次数清算

| 类型 | 次数 | 在哪 |
|---|---|---|
| **LLM 调用** | **6 次** | plan / consolidate / promote / demote / resolve / reflect 各 1 次 |
| **Embedding** | **0 次** | Sleep 不算 embedding(只读 staging 里现成的 embedding;但 consolidation 用了 pgvector `<=>` 算距离,**不调外部 API**) |
| **DB COMMIT** | **~10 次** | snapshot 1 + 每个 apply_xxx 1 + reflect 1 + swap 1 + N 个 consolidate / promote / demote 子 commit |
| **DB query 总数** | **50-200 个** | 取决于 archival 数量(consolidate O(N²)+其他 phase 各几个) |

### 延时分布

| Phase | 耗时(MVP 1000 archival) |
|---|---|
| ① snapshot | 100-500 ms |
| ② plan | 1-2 秒 |
| ③ consolidate | 3-10 秒(LLM + O(N²) 聚类) |
| ④ promote | 2-5 秒 |
| ⑤ demote | 2-5 秒 |
| ⑥ resolve | 2-5 秒 |
| ⑦ reflect | 2-4 秒 |
| ⑧ swap | 50-200 ms |
| **总计** | **~15-30 秒**(MVP 数据量),最差 5 分钟(budget) |

### Token 成本

6 次 LLM 调用,每次 input ~2-4K(prompt + 数据),output ~200-1000(JSON / 段落):
- 总 input ~15-25K tok
- 总 output ~2-5K tok
- DeepSeek 成本 ≈ **$0.004 - 0.008 一次 cycle**
- 每天最多触发几次(idle 30 min + cron 一次)→ **每天 cycle 成本 ≈ $0.02-0.05**

### 错误怎么传播

`run_sleep_cycle()` 整体 try/except:
```python
try:
    final_state = await graph.ainvoke(init_state)
except Exception as exc:
    logger.exception(...)
    try:
        async with Session() as session:
            await staging.cleanup_staging(session)
    except Exception:
        pass
    return {"status": "error", "error": str(exc)}
```

每个 phase 内部还有 `if state.get("aborted") or not _budget_ok(state): return state` 守卫——**budget 用完就跳过剩下 phase 直接走 swap**(swap 里 abort = cleanup_staging)。

→ **3 层防护**:phase 守卫 + cycle try/except + swap 里的 abort 分支。Sleep cycle 崩了 staging 一定被清,主表绝不污染。

### Awake 在 cycle 期间能不能服务?

**能,基本不阻塞**。

- snapshot:DROP/CREATE/INSERT staging 表,**不动主表**
- 6 个 phase:全部 UPDATE staging,**不动主表**
- swap:RENAME 拿 ACCESS EXCLUSIVE LOCK,**主表短暂阻塞**(几十-几百 ms)
- Awake 在 cycle 期间正常 INSERT 主表,这些行被 swap 的 step a 合并到新主表

唯一 race:`mark_archival_used` UPDATE use_count,如果 Sleep 也改了同一行,Awake 的 UPDATE 被覆盖。**MVP 接受**(use_count 误差小不影响下次 promote 决策)。

### §5 · 课后思考题

#### Q1:一次 `remember` 调用,**LLM 被调几次?embedding 被调几次?**

提示:画时序图,标注每个 LLM / embedding API 调用。算:
- **LLM**:Awake ReAct loop 至少 3 次("先想 → 选 search → 看结果 → 选 insert → done")
- **embedding**:至少 2 次(`search_archival` 把 query 转向量 + `insert_archival_fact` 把 content 转向量存库)
- **token 估算**:DeepSeek input 2K + output 200,$0.0006 一次

**思考方向**:**能不能省**?(线索:embedding cache;LLM 跳过 search 直接 insert;...)各自的取舍?

#### Q2:一次 sleep cycle,**8 phase 各自调几次 LLM**?

每 phase 大致:
- snapshot:0(纯 DB)
- plan:1
- consolidate:1(或 N=cluster 数,看实现)
- promote:1(或 N=candidate 数)
- demote:1
- resolve:1
- reflect:1
- swap:0

→ 总共 ~6-10 次 LLM,加 K 次 embedding(取决于新 archival 数)。

**思考方向**:如果 archival 攒到 200 条,promote 候选 50 条,**一个 prompt 装不下** 50 条。怎么 chunk?(线索:按 cluster 分批;按 tag 分批;top-K only)。chunk 后**怎么避免决策冲突**(两个 chunk 都想 promote 到同一 core block)?

#### Q3:如果 remember 调用进来的瞬间 sleep cycle 在 phase 3(consolidate),会怎样?

提示:
- Awake 写**主表**`archival_facts`(INSERT)
- Sleep 写**staging**`archival_facts_staging`(UPDATE)
- 两者**操作的是不同表**,所以 INSERT 不阻塞
- **但**:swap 时主表新增的这条 fact 在不在 staging?(读 §4.4 Q3 答案)

**思考方向**:Awake 和 Sleep 通过 "**主表 vs staging 表分离**" 实现伪并发——这个设计的**边界 case** 有哪些?(线索:swap 瞬间的 race;cleanup 失败的孤儿表;process kill 留下的 staging 残留)

---

# §6 · 四个最难的实现细节

> 这章不是"项目有什么 feature",是"项目里**最值得深挖的 4 个工程决策**"。每一个都能撑一段面试对话。

---

## §6.1 · Staging swap 的并发安全

### 问题

Sleep 要改几十行数据(merge + promote + demote + resolve),期间 Awake 还在服务用户。**怎么保证 Awake 永远看到一致状态**(不会读到 "consolidate 改了一半的 archival")?

### 我们的解(已在 §4.4 详讲,这里强调实现关键)

**核心:Sleep 全程在 `*_staging` 副本上工作,最后一瞬间 RENAME 切换。**

```python
# sleep/staging.py:80-86
for tbl in _STAGED_TABLES:
    staging = f"{tbl}_staging"
    tmp = f"{tbl}_tmp_swap"
    await session.execute(text(f"ALTER TABLE {tbl} RENAME TO {tmp}"))
    await session.execute(text(f"ALTER TABLE {staging} RENAME TO {tbl}"))
    await session.execute(text(f"ALTER TABLE {tmp} RENAME TO {staging}"))
```

### 三个关键设计点

#### ① 为啥三对 RENAME 不是两对

| 两对方案 | 三对方案 |
|---|---|
| `core_blocks → tmp; staging → core_blocks` | `core_blocks → tmp; staging → core_blocks; tmp → staging` |
| **中间一刻 `core_blocks` 名字不存在** | **全程 `core_blocks` 名字至少占着** |
| Awake `SELECT core_blocks` → 报 "relation does not exist" | Awake `SELECT core_blocks` → 等锁,然后读新表 |

→ **三对是为了 schema 名字连续性**。

#### ② 单 transaction 包住三对 RENAME

```python
await session.execute(...)  # 6 个 RENAME(2 表 × 3 对)
await session.execute(...)  # 2 个 TRUNCATE
await session.commit()      # 一次提交
```

如果分多个 transaction:中间某次失败 = 表名变成 `core_blocks_tmp_swap` 然后留在那永远不变回去 = **schema 损坏**。

单 transaction 保证:**要么全成功,要么 PG 自动回滚到 swap 前状态**。

#### ③ ACCESS EXCLUSIVE LOCK 的等待

RENAME 拿的是 PG 最高级锁:
- **阻塞所有** 其他事务(包括 SELECT)
- 必须等到主表上**所有现有 query 跑完**才能拿到锁
- 拿到后**全程独占**直到本 transaction COMMIT

实际行为:
- Awake 在 swap 瞬间 `SELECT archival_facts`:**短暂阻塞**(几十-几百 ms)直到 swap commit,然后继续(读新表)
- 极端 case:Awake 有个 5 秒慢 query 还在跑 → swap 等 5 秒拿不到锁 → 默认无 timeout 会一直等

**Mitigation 选项**(MVP 没做,生产化要做):
```sql
SET lock_timeout = '500ms';
```
swap 拿不到锁就放弃,cycle 失败回滚。下次 cycle 再尝试。

### 面试 30 秒口径

> "swap 用三对 RENAME(per table)在同一 transaction:`main → tmp, staging → main, tmp → staging`。三对是为了保证 `main` 名字全程占着,Awake 不会读到 'relation does not exist'。单 transaction 保证原子,要么全成要么 PG 自动回滚。代价是 RENAME 拿 ACCESS EXCLUSIVE LOCK 短暂阻塞 Awake——已知 trade-off,生产化加 lock_timeout mitigation。"

---

## §6.2 · Embedding 的事务边界(MVP 现状 + 设计意图)

### 现状(诚实版)

打开 `memory/store.py:155-178` 的 `insert_archival`,会看到:

```python
vec = await embed_text(content)       # ← 先调外部 API
fact = ArchivalFact(
    content=content,
    ...
    embedding=vec,                     # ← embedding 直接装进对象
)
session.add(fact)
await session.flush()                  # 拿 fact.id
session.add(MemoryOpsLog(...))
await session.commit()                 # fact + ops_log 一起 commit
```

**真实顺序**:
1. 先调 `embed_text(content)` 等阿里通义 API 返回 vector
2. **如果 API 失败 → 整个函数抛异常,fact 没入库**
3. 成功才创建 fact 对象 + add session

→ **目前并非"defer-write"**——embedding 成功才有 fact。**`embedding nullable` 是 schema 留了接口,代码没启用。**

### 为啥 schema 留接口

未来如果想真做 defer-write:

```python
# 假想的 defer-write 版本
fact = ArchivalFact(content=content, embedding=None)  # 先落,embedding 暂时 NULL
session.add(fact)
await session.flush()
session.add(MemoryOpsLog(...))
await session.commit()                                  # fact 已入库

try:
    vec = await embed_text(content)                    # 再补 embedding
    fact.embedding = vec
    await session.commit()
except Exception:
    pass                                               # 失败也没事,后台 backlog 补
```

好处:**embedding API 故障 ≠ 用户无法 remember**。fact 先入库(关键路径),embedding 异步补(次要路径)。

### 为啥 MVP 没启用

| 原因 | 解释 |
|---|---|
| 复杂度 | 需要后台 worker 定期扫 `WHERE embedding IS NULL` 补 |
| 风险 | embedding 暂时为 NULL 时,search 会跳过这条 fact(代码已有 `WHERE embedding IS NOT NULL`),用户感觉"刚记的找不到" |
| 收益 | 阿里通义 API 稳定性高,失败率 < 0.1% |

→ **MVP 选择"快速失败 + 让用户重试"**,而不是"defer-write + 后台修复"。Schema 留接口是为了**未来可演进**。

### 面试加分句

> "schema 里 embedding 是 nullable,意图是支持 defer-write 容错——fact 先入库,embedding 失败后台补。但 MVP 代码暂时是同步路径:embedding 失败 fact 不入库,让用户重试。这是个**有意的简化**,因为阿里通义 API 稳定性高,defer-write 的后台 worker 复杂度收益不平衡。schema 留接口保证未来想加 defer-write 不用改 DDL。"

→ **诚实承认 MVP 现状 + 说清 schema 设计意图** 比假装"我已经做了 defer-write" 加分。

---

## §6.3 · ops_log 与主表 mutation 的事务原子性

### 核心问题

写 fact 和写 ops_log 是不是**同一个 transaction**?如果不是,什么场景会出现 "改了主表没留日志" 或反过来?

### 答案:**同一 transaction**(读 `memory/store.py` 确认)

`insert_archival`(141-179 行):
```python
async def insert_archival(session: AsyncSession, ...) -> int:
    vec = await embed_text(content)
    fact = ArchivalFact(...)
    session.add(fact)                           # ① 加 fact
    await session.flush()                       # 拿 id, 但未 commit
    session.add(MemoryOpsLog(...))              # ② 加 ops_log
    await session.commit()                      # ③ 同一 commit
```

`soft_delete_archival`(182-208 行):
```python
fact.is_deleted = True                          # ① UPDATE fact
session.add(MemoryOpsLog(...))                  # ② 加 ops_log
await session.commit()                          # ③ 同一 commit
```

`write_core_block`(232-279 行):
```python
block.value = new_value                         # ① UPDATE core
block.version += 1
block.last_writer = actor
session.add(MemoryOpsLog(op_type='sleep_promote', ...))  # ② 加 ops_log
await session.commit()                          # ③ 同一 commit
```

**结论**:所有 Awake / Sleep 的 mutation 都是 **"主表改动 + ops_log INSERT 在同一 transaction"**。

### 这保证了啥

| 场景 | 保证 |
|---|---|
| 主表 INSERT 成功,ops_log INSERT 失败 | **不可能** —— 同 transaction,任一失败全回滚 |
| 主表回滚,ops_log 留下孤儿 | **不可能** —— 同上 |
| 进程崩在 ①② 之间 | **不可能** —— 没 commit 就崩,**两者都没写**(PG 事务回滚) |
| 进程崩在 ③ 之后 | **OK** —— 两者都成功写入 |
| 进程崩在 ③ 中间 | **OK** —— PG WAL 保证 atomic commit,要么全成要么全 rollback |

### `policy_violation` 的特殊处理

`write_core_block` 在 Awake 越权调时:
```python
if actor != "sleep_agent":
    session.add(MemoryOpsLog(op_type="policy_violation", ...))
    await session.commit()                      # ← 这里就 commit 了
    raise PermissionError(...)                  # ← 然后抛
```

→ **policy_violation 日志在抛异常前就已 commit**——这是有意的,**确保非法尝试一定留痕**。Awake 不知道自己被记了,但运维能看到。

### 为啥不用 outbox 模式 / 异步队列?

替代方案:**outbox** —— ops_log 先写 outbox 表,异步 worker 扫 outbox 写入真 log。

| 维度 | 直接同 transaction | outbox |
|---|---|---|
| 一致性 | 强(全成或全无) | 最终一致(outbox 已写,worker 还没消化) |
| 性能 | mutation 等 ops_log 写完 | mutation 不等 |
| 复杂度 | 低 | 高(worker / 重试 / dedup) |
| 失败模式 | ops_log 失败业务失败 | outbox 失败业务失败,worker 失败不影响业务 |

→ **MVP 选直接同 transaction**:简单 + 强一致。**生产化大 scale 可上 outbox**,但目前没必要。

### 面试 30 秒口径

> "所有 mutation 跟 ops_log 在同一个 SQLAlchemy session 一次 commit—— PG WAL 保证 atomic。这意味着不可能出现'改了主表没留日志'或'log 留了但没改主表'。代价是 ops_log INSERT 失败会回滚业务,但 ops_log 跟主表同库,失败率几乎为零。如果以后规模上来,可以演进到 outbox 模式实现最终一致 + 解耦,但 MVP 直接同 transaction 是正解。"

---

## §6.4 · APScheduler idle 计时在 process restart 后

### 问题

`sleep/scheduler.py:27` 把"上次 Awake 活动时间"存在**进程内存模块变量**:

```python
_last_awake_activity_monotonic: float = time.monotonic()
```

进程重启后:
- `time.monotonic()` 是相对时间(进程启动后秒数),**重启后从 0 开始**
- 重启后第一次 `_idle_seconds()` = 0,需要再等 30 分钟才会触发 cycle
- **极端 case**:user 9:00 mark_activity,12:00 系统重启,**到 12:30 才会 trigger**,实际 user 已经 3 小时没动了

### 这是 MVP 的 known issue

代码注释明说:
```python
# Module-level state (in-process; MVP single-user).
_last_awake_activity_monotonic: float = time.monotonic()
_cycle_running: bool = False
```

「MVP single-user」= 单进程 + 单用户,内存变量够用。多进程 / 重启就崩。

### 三种修复方案

**方案 A:写 DB**
```python
async def mark_awake_activity():
    async with session_factory()() as session:
        await session.execute(text(
            "INSERT INTO scheduler_state (key, ts) VALUES ('last_activity', now()) "
            "ON CONFLICT (key) DO UPDATE SET ts = EXCLUDED.ts"
        ))
        await session.commit()
```
- pros:重启恢复
- cons:**每次 MCP 调用 +1 DB write**(写放大)

**方案 B:启动时从 ops_log 推算**
```python
async def init_scheduler():
    async with session_factory()() as session:
        last_op = await session.execute(text(
            "SELECT ts FROM memory_ops_log WHERE actor='awake_agent' ORDER BY ts DESC LIMIT 1"
        ))
        last_ts = last_op.scalar_one_or_none()
        if last_ts:
            # 把内存变量初始化成"距离上次 op 已经过去 X 秒前"
            _last_awake_activity_monotonic = time.monotonic() - (datetime.utcnow() - last_ts).total_seconds()
```
- pros:**零 write 放大**,只在启动时算一次
- cons:`recall` 不写 log → idle 估算偏旧

**方案 C:写文件**
```python
def mark_awake_activity():
    Path("/var/run/dream-last-activity").write_text(str(time.time()))
```
- pros:简单,无 DB 依赖
- cons:文件系统竞争 / NFS 不稳

→ **推荐方案 B**(零写放大,生产化推荐),配 cron 兜底(每天 03:00 强制跑,即使 idle 计时错也最多延迟 1 天)。

### 进程被 kill -9 在 cycle 跑到一半会怎样

| 状态 | 结果 |
|---|---|
| `_cycle_running = True` 但进程没了 | 重启后 `_cycle_running = False` (内存变量重置),下次 trigger 正常 |
| Sleep 跑到 phase 4 promote,改了 staging 一半,进程崩 | staging 表里有"半成品"数据,但**主表没动** |
| 进程重启 | 下次 cycle 的 snapshot 会 `DROP TABLE IF EXISTS *_staging CASCADE` 把半成品全清 |
| **数据安全性** | **主表绝对安全**(staging 是隔离的),最多丢这次 cycle 的工作 |

→ **staging 设计的副效益**:cycle 不可中断也没关系,**死了清掉重来**。

### 面试 30 秒口径

> "MVP 把 idle 计时存进程内存变量,重启会归零。这是 known issue,生产化方案有三:写 DB(写放大)、启动时从 ops_log 推算(推荐,零写放大)、写文件(简单但脆弱)。**进程崩在 cycle 中也没事**——staging 表是隔离的,主表绝对安全,下次 cycle 重新 snapshot 会清掉半成品。这是 staging 设计的副效益:cycle 不可中断 = 死了重来。"

---

## §6 · 课后思考题

#### Q1:**ops_log + 主表 mutation 是同一 transaction 吗?**

读 `memory/store.py:insert_archival` 自己看。提示找:
- 是不是同一个 `async with session_factory()() as session:` block?
- `session.commit()` 调几次?
- 中间有没有 `await session.flush()` 然后挂起的可能?

**思考方向**:**如果是同 transaction**——好处是原子,坏处是 ops_log 失败会回滚业务写(可接受吗?);**如果不是**——会出现什么 inconsistency case?面试官常问:**"假设你能 root 这台机器,主表 INSERT 完 ops_log INSERT 前杀进程,DB 是什么状态?"**

#### Q2:**进程重启后 idle 计时归零会怎样?**

极端 case:
- user 早上 9 点 mark_activity
- 中午 12 点系统重启
- 重启后 idle = 0 → 等到下午 12:30 才触发 cycle
- 实际**用户已经 3 小时没动了**,本该立刻 trigger

**思考方向**:你会怎么持久化 idle 状态?(线索:写 `last_activity_at` 到 DB / Redis / 文件)。每次 mark 都 round-trip 又会怎样?(写放大)。**有没有不持久化也能解决的方案**?(线索:启动时扫一次 DB,看 ops_log 最近一条时间;启动后等 30 分钟才允许触发 cycle)

#### Q3:**embedding API 长期挂掉(阿里通义故障 1 小时)**会怎样?

具体追:
- `insert_archival` 调 `embed_text()` 报错——row 写没写进去?
- `search_archival` 调 `embed_text()` 报错——抛异常还是降级到关键词搜索?
- Sleep `consolidate` 找 cluster 调向量 query——pgvector 用 NULL embedding 怎么 ORDER BY?

**思考方向**:画一张表,**每个用到 embedding 的代码路径在故障下的行为**。然后给**最小修复方案**(circuit breaker / 关键词 fallback / 失败 row 队列 + 后台补)。**这是个高频面试题**——"你这依赖的外部服务挂了怎么办"。

---

# §7 · 已知 trade-off

> 这章是项目最容易被面试官攻击的部分,所以**主动把它们摊在桌面上**——比被问到才挤牙膏强百倍。
>
> 每个 trade-off 给:**症状 + 为啥这么做 + 什么时候必须修 + 怎么修**。

---

## ① Invariants 散落 6 处

### 症状

应用层 6 个 invariant 没有集中强制,散在 6 个文件靠程序员自律(§3.5):

| Invariant | 强制位置 |
|---|---|
| 只有 sleep_agent 能写 core | `memory/store.py:245` 运行时 if |
| 每次 mutation 留 ops_log | 各 mutation 函数手动 `session.add(MemoryOpsLog(...))` |
| 同时最多一个 sleep cycle | `sleep/scheduler.py:44-47` 布尔 + APScheduler max_instances=1 |
| Sleep 全程写 staging | `sleep/tools.py` SQL 拼 `_staging` 后缀,**靠自律** |
| Awake 操作完调 mark_awake_activity | `mcp_server.py:25` 一处 wrap |
| staging swap 单 transaction | `sleep/staging.py` 全在一个 session |

### 为啥 MVP 这么做

- 集中强制(AOP / Repository pattern)**前期成本高**,代码量翻倍
- MVP 一个人写一个人维护,自律够用
- 真正的护城河是 **review 时盯紧 + Sleep test 覆盖**

### 什么时候必须修

任何下面情况:
- **多人协作** —— 新加路径忘 invariant 就违反
- **开源给别人 PR** —— 外部贡献者不知道这些隐式约定
- **scale 到多服务** —— 跨服务调用没法靠自律

### 怎么修(从轻到重)

| 方案 | 工作量 | 强制级别 |
|---|---|---|
| Repository 层 wrap(Sleep 写经 StagingRepo,只暴露 staging API) | 中 | **结构上**不可能违反 |
| AOP / 装饰器(mutation 函数加 `@audit_logged` 自动写 ops_log) | 中 | 函数级别 |
| import-linter 架构测试(验证 `sleep/*.py` 不能 import 主表写函数) | 低 | CI 卡 |
| PG Row Level Security (RLS) DB 强制 Awake 角色不能 UPDATE core_blocks | 高 | **DB 终极保险** |

---

## ② Staging swap 短暂阻塞 Awake

### 症状

`ALTER TABLE ... RENAME` 拿 `ACCESS EXCLUSIVE LOCK`,**阻塞所有 SELECT**(包括正在 ReAct loop 的 Awake)。

### 为啥 MVP 接受

- 阻塞时间短(几十-几百 ms)
- cycle 在 idle 时段触发,自然冷期
- 用户感知不到(本来就 idle)

### 什么时候必须修

- Awake 流量上升(QPS > 10),阻塞累积可见
- 有长查询(几秒级)挡住 swap,cycle 失败累积

### 怎么修

```sql
-- Mitigation 1: 给 swap 加 lock_timeout
SET lock_timeout = '500ms';
-- swap 失败 cycle 回滚,下次再试
```

```sql
-- Mitigation 2: 用 view 替代物理 RENAME
CREATE OR REPLACE VIEW core_blocks AS SELECT * FROM core_blocks_v_current;
-- swap = 切换 view 指向(更轻量)
```

```python
# Mitigation 3: 把 swap 拆成多个小 RENAME(每张表独立 transaction)
# 失去原子性,但缩短单次锁时间
```

---

## ③ 单用户写死(`user_id` 不存在)

### 症状

整个 codebase 找不到 `user_id` 字段,MCP / store / sleep 都默认"就一个 user"。

### 为啥 MVP 这么做

- 加 `user_id` = 3 张表全部加列 + 全部 query 加 WHERE + 索引复合
- MVP 验证架构正确性不是 multi-tenant
- **过早 multi-tenant 比晚加难收拾**(假设藏在很多地方)

### 什么时候必须修

任何需要 ≥ 2 user 的时候 —— **现在没需求**,真要时再加。

### 怎么修

详见 §4.5 取舍 4 的两种方案(加列 vs 独立 schema)。

---

## ④ Cycle 不可中断 + 进程崩留 staging 孤儿

### 症状

Sleep cycle 一旦开始就跑完(15 秒-5 分钟),没法手动 abort。进程 kill -9 在 cycle 中 → staging 表留半成品。

### 为啥 MVP 这么做

- 中断逻辑复杂(每个 phase 都要 check signal)
- 实际 cycle 短(平均 < 30 秒)
- staging 孤儿**不会污染主表**,下次 snapshot 会清

### 什么时候必须修

- cycle 平均时长涨到分钟级(数据量上来)
- 需要支持运维"现在停一下"(比如 DB migration)

### 怎么修

```python
# 加 asyncio.CancelledError 处理
async def run_sleep_cycle():
    try:
        await graph.ainvoke(init_state)
    except asyncio.CancelledError:
        await staging.cleanup_staging(session)
        raise
```

+ 给 graph 加 conditional edge "abort_check" 在每个 node 之间检查信号。

---

## ⑤ ops_log 无 retention

### 症状

`memory_ops_log` 无限增长,没归档 / 删除策略。

### 为啥 MVP 这么做

- 一年才几万行,几年才百万行
- 审计场景**永久保留更安全**
- 归档 / 分区有运维复杂度

### 什么时候必须修

- 表到 100 万行,B-tree 索引插入开始变慢
- 想做长期分析(每月活跃 / 模式识别),冷热数据分离

### 怎么修

```sql
-- 方案 A: PG declarative partitioning by month
CREATE TABLE memory_ops_log (
    ...
    ts TIMESTAMPTZ NOT NULL
) PARTITION BY RANGE (ts);

CREATE TABLE memory_ops_log_202604 PARTITION OF memory_ops_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
-- ... 每月新建一个 partition
-- 老 partition DETACH 后归档到 S3
```

```sql
-- 方案 B: 简单点,跑定时 job 把 90 天前的搬到 ops_log_archive
INSERT INTO ops_log_archive SELECT * FROM memory_ops_log WHERE ts < now() - INTERVAL '90 days';
DELETE FROM memory_ops_log WHERE ts < now() - INTERVAL '90 days';
```

---

## ⑥ Embedding 失败容错弱(无 backlog 补)

### 症状

`insert_archival` 先调 embedding API 再落 fact,API 失败 = fact 不入库,用户得手动重试。

### 为啥 MVP 这么做

- 阿里通义稳定性高,失败率 < 0.1%
- defer-write + backlog worker 复杂度收益不平衡

### 什么时候必须修

- 嵌入式部署(网络不稳)
- 切换到本地 BGE-m3 embedding(GPU OOM 偶尔失败)
- 用户重要时刻 remember 失败(不可容忍)

### 怎么修

详见 §6.2 defer-write 方案。

---

## ⑦ Idle 计时不持久化(进程重启丢)

### 症状

`_last_awake_activity_monotonic` 在内存,重启归零,下次 cycle 延迟 30 分钟。

### 为啥 MVP 这么做

- 单进程 + 单用户场景够用
- 写 DB 有写放大

### 什么时候必须修

- 多进程部署
- 频繁部署 / 重启
- HA 需求

### 怎么修

详见 §6.4 三种方案(推荐方案 B:启动时从 ops_log 推算)。

---

## ⑧ 没有 evaluation harness

### 症状

Sleep prompt 改了**不知道好坏**:promote 决策对不对?consolidate merge 合理吗?reflect 段落质量?**没有 ground truth 测试集 + 评分**。

### 为啥 MVP 没做

- ground truth 数据要人工标注,工作量大
- LLM-as-judge 不确定性高,需要校准
- 业务还没跑起来,没数据可标

### 什么时候必须修

任何 prompt 迭代频繁的时刻 —— **改 prompt 不能靠肉眼看几个例子**。

### 怎么修

```python
# Day 05+ 设想
class EvalCase:
    setup_archival: list[dict]          # 注入这些 archival 到 staging
    expected_action: dict               # 期望 Sleep 输出的 action
    judge_prompt: str                   # LLM-as-judge 的评分 prompt

# 跑 eval:每改一次 prompt,自动对 50 个 case 跑分
async def run_eval_suite():
    for case in suite:
        setup_staging(case.setup_archival)
        actual = await run_sleep_phase(...)
        score = await llm_judge(case.expected_action, actual, case.judge_prompt)
        ...
```

参考 OpenAI Evals / Anthropic 的 LMSys 框架。

---

## ⑨ 没有 backup / restore 方案

### 症状

PG 挂了 = memory 全没。**没有 daily backup 脚本**。

### 为啥 MVP 没做

- 本地开发数据丢了无所谓
- 生产化才需要

### 怎么修

```bash
# Cron daily
pg_dump -Fc dream | aws s3 cp - s3://dream-backup/$(date +%F).dump

# 恢复
aws s3 cp s3://dream-backup/2026-06-15.dump - | pg_restore -d dream
```

或上 PG 内置 streaming replication 到 standby。

---

## ⑩ Consolidate 用 O(N²) 朴素聚类

### 症状

`sleep/tools.py:find_consolidation_clusters` 是**贪心 O(N²)**,1000 archival 一次跑就 100 万次 pgvector 距离计算。

### 为啥 MVP 这么做

代码注释明说:"Naive O(N^2) for MVP. For MVP archival sizes (<1000), this is fine. Day 05+: replace with HNSW + clustering algorithm."

### 什么时候必须修

- archival 攒到 5000+ → 一次 cycle 几分钟
- archival 攒到 10000+ → cycle 超 budget (5 min) 直接 timeout

### 怎么修

```python
# 方案 A: 用 HNSW + 阈值剪枝
# 不用每对都算,只看每行的 top-K 近邻
SELECT a.id, b.id, a.embedding <=> b.embedding AS dist
FROM archival_facts_staging a, LATERAL (
    SELECT id, embedding FROM archival_facts_staging
    WHERE id > a.id AND is_deleted=FALSE
    ORDER BY embedding <=> a.embedding LIMIT 5
) b
WHERE a.embedding <=> b.embedding < 0.15;
```

```python
# 方案 B: DBSCAN / HDBSCAN 聚类(sklearn)
# 把所有 embedding 拉出来跑聚类算法,只对同 cluster 内成员考虑 merge
```

---

## §7 · 章末小结:面试反 BS

| 攻击 | 反击 |
|---|---|
| "这看着像 toy 项目" | "scope 收窄是有意——核心设计原则在 1 user 和 1M user 都成立" |
| "为啥 invariant 不集中强制" | "MVP 阶段自律够,生产化有 4 个方案(Repository / AOP / linter / RLS)" |
| "embedding 挂了你 fact 就丢了" | "现状是这样,schema 留了 defer-write 接口,什么时候启用看 embedding API 稳定性" |
| "staging swap 你阻塞 Awake" | "对,阻塞 < 100ms 且在 idle 时段。已知 trade-off,有 3 种 mitigation 方向" |
| "为啥不上 multi-tenant" | "不是技术不足,是 MVP scope。两种改造方案各自取舍我能讲(详见 §4.5)" |
| "为啥不写 backup" | "本地开发不需要,生产化加 pg_dump cron + S3 即可" |
| "为啥 consolidate 是 O(N²)" | "MVP archival < 1000 够用,代码注释明说 Day 05+ 升 HNSW" |

### 面试 30 秒口径

> "这项目有 10 个已知 trade-off,我能逐个讲:为啥这么做、什么时候必须修、怎么修。**没有任何一个是技术不足导致的,全是 MVP scope 主动选择**。区别是个**有意识的工程师**还是**没想清楚的项目**——我能讲清楚每个取舍背后的原因。"

### §7 · 课后思考题

> 这章是项目最容易被面试官攻击的部分,**先自己练**。

#### Q1:你能自己列 3 个项目硬伤吗?

不看上面那张表,**先在纸上写**。写完跟我下次给的完整 10 条对比——你能想到几条 / 漏掉哪几条 / 想到我没想到的有没有?

#### Q2:每个伤,**给一个真实可执行的修复方案**(不要空话)

❌ "加监控" "做更严格的测试" "考虑使用分布式锁"——这都是面试**死刑**
✅ "用 PG advisory lock,sleep cycle 开始时 `SELECT pg_try_advisory_lock(42)`,失败就跳过本轮;cycle 结束 `pg_advisory_unlock`;进程异常退出 PG 自动释放" ——具体可执行

**思考方向**:挑 3 个你自己列的伤,**写出可以直接 git commit 的方案**(伪代码级别)。

#### Q3:面试官说"这看着像个 toy 项目",你怎么 reframe?

不要慌不要否认——**承认 + reframe**。

提示骨架:
> "对,这是个 single-user, single-instance, MVP 阶段的项目。**scope 收窄是有意的**:Letta 架构 + read-only primary + staging swap 这些核心设计原则,在 1 user 和 1M user 都成立。我专注**架构正确性而不是 scale**。multi-tenant / HA / backup 是已知 trade-off 不是技术不足,**这些功能加上去是工程量问题不是设计问题**。换句话说,**我把核心设计原则跑通,scale 是后续路径上的工程任务**。"

→ 你写一版自己的话术。下次给你打分。

---

# §8 · 面试 18 连问

> 18 题分四组,每题给:**原话 / 答题骨架 / 加分点 / 死刑陷阱 / 追问 fallback**。
>
> 用法:**每题口头过一遍 30-60 秒**,卡壳的题做标记下次重点过。

---

## 组 1:项目背景题(5 题)

### Q1:30 秒讲下这个项目

**骨架**:
> "Mneme 是给 Claude Code 装的跨 project 长期记忆服务,通过 MCP 协议接入。严格按 Letta sleep-time compute paper 实现 **Awake / Sleep 双 agent + read-only primary** 架构:Awake 实时响应 remember / recall,只能写 archival;Sleep 在 idle 时跑 consolidation / promotion / reflection,是 core_blocks 的唯一 writer。并发用 staging snapshot + atomic swap 解决。技术栈 Python + LangGraph + PostgreSQL + pgvector + DeepSeek。"

**加分点**:
- 主动提 "跟 Claude Code 自带 memory 互补"(显示懂边界)
- 提 Letta paper 编号(arxiv 2504.13171)→ 显示真读过
- 提 "read-only primary 是 Letta 借 DB 术语但语义反过来"

**死刑陷阱**:
- 说成 "聊天机器人 + 记忆" → ❌ Mneme 不跟人聊
- 说成 "RAG 知识库" → ❌ Mneme 不索引文档
- 说成 "ChatGPT Memory 替代品" → ❌ 是 MCP 生态补 Claude Code 留白

**追问 fallback**:"你能展开讲下 read-only primary?" → 跳 Q6

---

### Q2:为啥不直接用 Claude Code 自带 memory / ChatGPT Memory / mem0?

**骨架**:
> "Claude Code 的 CLAUDE.md 和 per-project auto memory 都是 **per-project** 的,**跨 project 的'关于用户这个人' 是空白**。我项目专门补这块。
>
> ChatGPT Memory 是闭源 SaaS,Claude Code 用不了,而且它是通用产品,不是 IDE 场景。
>
> mem0 / cognee 是好项目,但它们是**通用记忆框架**,我项目是 **MCP 协议 + Letta paper 严格实现**,差异在'读 Letta 论文按设计实现' vs '调包用别人封装'。简历叙事不一样。"

**加分点**:
- 给具体例子说 Claude Code 自带 memory 不覆盖什么(跨 project 偏好 / 教训)
- "fork mem0 改改 vs 自实现 Letta paper"——后者是项目存在的理由

**死刑陷阱**:
- 攻击 ChatGPT Memory / mem0 → ❌ 不需要踩别人
- "他们做不好" → ❌ 应该说 "他们做的事不一样"

**追问 fallback**:"那你跟 mem0 有什么本质区别?" → 跳 Q18

---

### Q3:你是 Java 后端实习,为啥 Python?

**骨架**(详见 §2.1):
> "求职双线投——Java backend 主线,这个项目是差异化补充。Java 我有 Thunderbit 实习背书,不需要再用项目证明常规 backend。
>
> 这个项目要展示 **AI agent + 架构设计 + 系统设计** 能力,Python 是行业主场:LangGraph / MCP Python SDK / Letta 引用实现全在 Python。用 Java 反而被追'为啥不用主流栈',故事更难讲。
>
> 项目 90% 复杂度不在语言,在 read-only primary 怎么落地、staging swap 怎么不阻塞、Sleep cycle 8 阶段怎么协调。这些 Java 重写也是同一套架构。"

**加分点**:
- 提具体语言生态差距(LangChain4j 落后 2-3 版本)
- 强调"差异化补充" → 反 BS 自己技术单一

**死刑陷阱**:
- "Python 写起来快" → ❌ 听上去懒
- "Java 我已经会了无聊" → ❌ 听上去傲

**追问 fallback**:"Python async 你 OK 吗?" → 跳 Q11

---

### Q4:这项目你做了多久,目前完成度?

**骨架**(诚实版,需根据实际填):
> "断断续续 X 周。完成度:**核心架构跑通**——MCP server / Awake ReAct / Sleep 8 phase / staging swap 都跑过端到端 dogfooding。**已知 trade-off 10 个**(详见我项目 docs/STUDY-NOTES.md §7)。**没做的**:multi-tenant、HA、eval harness、backup——这些是已知 scope 外,不是技术不足。"

**加分点**:
- 主动说"已知不做什么"(显示有 scope 概念)
- 主动 reference 自己的 trade-off 文档
- 不夸大完成度("100% 完成"听上去假)

**死刑陷阱**:
- "差不多完成了" → ❌ 模糊话术显示没量化
- "还在 polish 一些小问题" → ❌ 听上去逃避问题
- "完整生产就绪" → ❌ 显然不是,会被追问验证

**追问 fallback**:"trade-off 你最想修哪个?" → 准备 §7 任选一个展开

---

### Q5:项目里你做的最难的决策是什么?

**骨架**(挑一个真的难的,不要装):
> "**Sleep 用 StateGraph 不用 create_react_agent**——很多人第一反应是'两个 agent 都用 ReAct 一致'。我反复想了几天,最后选 StateGraph,理由是 Sleep 8 阶段有严格状态依赖(snapshot 必须先、swap 必须后),让 LLM 自由调度有数据损坏风险。Anthropic Building Effective Agents 论文明确建议'可预测性 > 灵活性的场景用 workflow'。这就承认了 Sleep 严格说是 **agentic workflow** 不是 pure agent。**主动承认 + 解释为啥是对的选择**——这是我项目里最难的决策,因为它要承认架构上的'不一致'但论证其合理性。"

**加分点**:
- 选个**真的有思考深度**的决策(不要选"用 Python")
- 主动承认决策的"另一面"(Sleep 不是 pure agent)
- 引用论文支持

**死刑陷阱**:
- 选个**显而易见**的决策 → 显得没决策能力
- "都很难选" → ❌ 模糊话术

**追问 fallback**:"你说 Sleep 是 agentic workflow,工作流和 agent 区别是啥?" → 跳 §2.2 Q4 的 Anthropic 三层分类

---

## 组 2:架构 / 设计题(5 题)

### Q6:Letta 的 read-only primary 是啥?为啥这么设计?

**骨架**(详见 §2.2 Q1):
> "primary 指主 agent(Awake),read-only 是说它**对 core_blocks 只读**。Letta 借 DB replication 术语但语义反过来——DB 世界 primary 是能写的,Letta 世界 primary 不能写 core,只能 Sleep 写。
>
> 设计目的:**防止实时 agent 一时冲动污染用户画像**。Awake 是实时的可能错的,让它只能写'小水池'(archival),想进'大水池'(core)必须等 Sleep 慢慢审。这是**两道闸门**——单次错误不直接进核心画像。"

**加分点**:
- 用"水池"类比解释
- 提"信号驱动":archival 的 use_count / confidence 给 Sleep 喂数据,Sleep 据此 promote

**死刑陷阱**:
- 把 primary 当 DB primary 解释 → ❌ 完全反了

**追问 fallback**:"那 Awake 怎么强制只读 core?" → 跳 §3.5 invariants(运行时 if + raise PermissionError + 留 policy_violation 日志)

---

### Q7:Awake 和 Sleep 怎么分工?为啥不合一个 agent?

**骨架**:
> "**Awake 实时响应**——MCP tool 进来,ReAct loop 跑几次决策返回。秒级。**Sleep 后台自主**——APScheduler 检测 idle 30 分钟或每天 03:00 触发,跑 8 阶段 pipeline。分钟级。
>
> 不合一个 agent 的根本理由:**两种工作的时间尺度和决策粒度完全不同**。Awake 要快,LLM 一次只决策一步;Sleep 要稳,要做'consolidate 几十条 archival'这种重决策。合一个 agent = 强迫一个 LLM 既快又稳,反而都做不好。
>
> Letta paper 把这命名为 'sleep-time compute'——专门为这种'重决策放到后台'设计。"

**加分点**:
- 提 wall-time + decision 粒度对比
- 提 'sleep-time compute' 概念名

**死刑陷阱**:
- "为了简单"→ ❌ 听上去懒,实际是为了正确

**追问 fallback**:"Sleep 跑的时候 Awake 还能工作吗?" → 跳 §4.4 staging swap

---

### Q8:Staging swap 在解决什么问题?为啥不直接长事务?

**骨架**(详见 §6.1 + §4.4):
> "**核心问题**:Sleep 改几十行数据期间,Awake 要继续服务。**怎么保证 Awake 永远看到一致状态**(不会读到改了一半的 archival)。
>
> Staging swap:Sleep 全程在 `*_staging` 副本上工作,最后一瞬间三对 RENAME 切换。**读 / 写永不阻塞**(swap 瞬间几十 ms 例外)。
>
> 不用长事务的理由:长事务期间所有读 / 写**都阻塞**,MVCC dead tuples 堆积,vacuum 卡。staging 唯一缺点是实现复杂,其他维度全胜。"

**加分点**:
- 主动提"swap 瞬间 RENAME 拿 ACCESS EXCLUSIVE LOCK 短暂阻塞"——诚实
- 提 step a 处理 cycle 期间主表新插入行
- 提三对 RENAME 不是两对(中间名字连续性)

**死刑陷阱**:
- 说"全程无锁" → ❌ swap 瞬间是有锁的
- 不知道 ACCESS EXCLUSIVE LOCK → ❌ 显示对 PG 不熟

**追问 fallback**:"那 cycle 期间 Awake 又插入新 archival,这些会丢吗?" → 跳 §6.1 解释 step a 的 INSERT ... SELECT ... WHERE created_at > snapshot_ts

---

### Q9:数据模型为啥 core / archival 分两张表?

**骨架**(详见 §4.5 取舍 1):
> "字段差异太大——core 有 char_limit / version / 5 固定 label;archival 有 embedding 1024 维 / use_count / is_deleted / confidence。合一张表 50% 字段都得 NULL,索引规则要 partial,查询代码要带 type 判断。
>
> 更重要:**这两类信息演化方向不同**。core 是用户画像固定 5 块,archival 是无限增长 fact。合表后改 schema 互相牵制。
>
> 这跟 Letta paper 的 'core memory vs archival memory' 抽象一致——他们做了好多年这个判断我没必要重新发明。"

**加分点**:
- 类比"桌面便签 vs 仓库纸箱"
- 提"core 永远 5 条全读 / archival 千-万条按需检索"

**死刑陷阱**:
- "因为不一样" → ❌ 没说清不一样在哪

**追问 fallback**:"那 core 和 archival 有没有关联字段?" → 跳 §4.5 取舍 2:**故意不加 FK**

---

### Q10:你这架构可观测性怎么做?怎么知道 Sleep 跑对了?

**骨架**:
> "三个工具:
>
> 1. **`memory_ops_log` 全量审计**——每次 mutation 都留 `before_value` / `after_value` / `reason`。Sleep 跑完一次 cycle 我直接 `SELECT * FROM memory_ops_log WHERE ts > xxx ORDER BY ts` 看每一步改了啥、LLM 给的理由是啥。
> 2. **Sleep cycle 返回 result dict**——每个 phase 的 action 数量、reflection 段落 preview 都在 `run_sleep_cycle()` 返回值,scheduler 落 log。
> 3. **`last_writer` 字段自检**——core_blocks 每行有 last_writer,如果出现 `WHERE last_writer != 'sleep_agent'` 立即报警(invariant 被绕过)。
>
> **没做的**:metrics dashboard、LLM eval harness、prompt regression test。这是 §7 列出的 known trade-off,生产化要补。"

**加分点**:
- 同时说有 + 没有(显示自知边界)
- reference 自己的 §7 trade-off 文档

**死刑陷阱**:
- "用 Prometheus + Grafana" → ❌ 没做就别撒谎
- "充分监控" → ❌ 模糊话术

**追问 fallback**:"那 LLM prompt 改了你怎么知道好坏?" → 诚实"现在靠肉眼,§7 ⑧ 列了 eval harness 是 known TODO"

---

## 组 3:实现 / 取舍题(5 题)

### Q11:Python async 你 OK 吗?asyncio.gather 用过吗?

**骨架**:
> "OK。这项目全 async:Starlette + asyncpg + SQLAlchemy 2.0 async + APScheduler AsyncIOScheduler + LangGraph ainvoke。
>
> `asyncio.gather` 用过——但**这项目刻意没大量用**。原因:Sleep 的 8 phase 是**顺序**的(有状态依赖),Awake 的 ReAct loop 是 LangGraph 内部管理。我用 async 主要是 IO 不阻塞事件循环,不是为了并发跑多个 task。
>
> 真要 gather 的场景:embedding 多文本批量(`embed_texts`),但代码里用的是 `aembed_documents` 一次 batch,不需要 gather。"

**加分点**:
- 区分"async 是为不阻塞" vs "async 是为并发"
- 提具体没用 gather 的理由

**死刑陷阱**:
- 吹"重度并发"→ ❌ 不是事实
- 不知道 ainvoke 跟 invoke 区别 → ❌ 显示不熟 LangGraph

**追问 fallback**:"asyncio 嵌 gather 容易死锁吗?" → 答"嵌 for + gather 没问题,但 gather 内调阻塞 IO(用了 sync DB driver)会卡事件循环,要么用 asyncpg 要么 run_in_executor"

---

### Q12:pgvector 的 HNSW 跟 IVF 你怎么选?

**骨架**(详见 §2.3 Q2):
> "我选 HNSW。
>
> **HNSW**(我用的)分层图,O(log N),召回率 > 95%,内存占用高。**IVF** 簇 + 倒排,召回率 85-90%,内存占用低。
>
> 我项目规模 1000-10000 archival,**内存不是问题**;**读 100 : 写 1** 适合 HNSW;**user model 不允许漏**(漏一条可能下次 Sleep 没 promote 成 core)所以要高召回。
>
> 如果项目规模到亿级 vector + 强写 + 容忍小漏,会换 IVF 或专用向量库(Milvus / Qdrant)。"

**加分点**:
- 主动给"如果规模变了我会换"——显示有 scale awareness
- 提 IVF 的写入快(适合 stream ingestion)

**死刑陷阱**:
- 只说"HNSW 更好" → ❌ 没说为啥适合**我的场景**
- 不知道 IVF 是啥 → ❌ 准备不足

**追问 fallback**:"HNSW 索引 build 慢吗?" → 答"是,1 万行级几十秒,亿级要几小时。MVP 无所谓"

---

### Q13:LangGraph 的 StateGraph 你为啥不用 conditional edges?

**骨架**:
> "MVP 没用,留接口。**理由**:8 phase 顺序是固定的(snapshot → plan → consolidate → ... → swap),没有'根据 LLM 输出跳到不同节点'的场景。conditional_edges 加进来反而让代码复杂。
>
> 但**留了演进空间**——节点之间不是用 if/else 而是 `g.add_edge(START, "snapshot")` 这种 DSL,未来要 conditional 直接加 `g.add_conditional_edges(...)`。比 if/else 强 的地方在**显式声明流程图**,debug + 改流程都直观。"

**加分点**:
- 主动说"MVP 没用但留接口"
- 解释为啥 LangGraph DSL > if/else

**死刑陷阱**:
- "因为简单" → ❌ 应该说"目前不需要"

**追问 fallback**:"那你 plan phase 决定跳过某些 phase 怎么实现?" → 答"`if 'consolidate' not in state['plan']: return state` 在每个 phase node 开头,逻辑性 skip 不是图结构性 skip"

---

### Q14:embedding 失败你怎么 handle?

**骨架**(详见 §6.2):
> "**MVP 现状是 fail-fast**:`insert_archival` 先调 embedding,失败抛异常,fact 不入库,MCP 返回 error,Claude Code 让用户重试。
>
> **schema 留了 defer-write 接口** —— `embedding` 列是 nullable,意图是 fact 先入库 embedding 后台补。MVP 没启用是因为阿里通义稳定性高(失败率 < 0.1%),defer-write + backlog worker 的复杂度收益不平衡。
>
> 真要修:fact 先 insert with embedding=NULL → commit → try embed → 成功 UPDATE,失败放队列后台 retry。`search_archival` 跳过 embedding IS NULL 的行(代码已有这逻辑)。"

**加分点**:
- 诚实承认 MVP 现状不是 defer-write,但说清意图
- 给具体演进方案

**死刑陷阱**:
- 说"我已经做了 defer-write" → ❌ 代码不是,会被识破
- "重试就行" → ❌ 没说在哪重试

**追问 fallback**:"阿里通义挂了你的 recall 还能用吗?" → 答"recall 也会失败,因为要把 query embed 成向量;可以降级到关键词搜(`WHERE content ILIKE '%query%'`),MVP 没做"

---

### Q15:这套架构 multi-tenant 怎么改造?

**骨架**(详见 §4.5 取舍 4):
> "两种方案分档:
>
> **< 100 user**:每个 user 独立 PG schema(`CREATE SCHEMA user_xxx` + `SET search_path TO user_xxx`)。结构上隔离,query 不可能跨 user,但 schema 多了 DDL migration 痛苦。
>
> **100-10000 user**:3 张表加 `user_id` 列 + 索引复合。所有 query 强制带 user_id,运维简单但代码层要严防漏 user_id。
>
> **> 10000 user**:多实例分片,每个 PG 实例承担 N 个 user。
>
> **MVP 没做不是技术不足是 scope** —— 加 user_id 涉及 3 表 + 全 query + 索引 + agent 注入。MVP 写死 'userjyx',真要 multi-tenant 时按规模选方案。"

**加分点**:
- 按规模分档(显示有 scale 思维)
- 主动提"现在做反而难真 multi-tenant 化"

**死刑陷阱**:
- "直接加 user_id" → ❌ 没说有几种方案
- "用 Kubernetes" → ❌ 跑题

**追问 fallback**:"独立 schema 会不会 DDL migration 太痛苦?" → 答"对,但有工具(Alembic 多 schema 模式 / Liquibase parameterized changeset)"

---

## 组 4:反 BS 题(3 题)

### Q16:你这看着像 toy 项目,scale 怎么办?

**骨架**(详见 §7 章末小结):
> "对,这是 single-user / single-instance / MVP 项目。**scope 收窄是有意**,不是技术不足。
>
> **核心设计原则**——Letta read-only primary、staging swap、ops_log audit、信号驱动 promote / demote——这些在 1 user 和 1M user 都成立,**架构正确性跟 scale 无关**。
>
> **scale 是工程任务不是设计问题**:multi-tenant 改造、HA 部署、ops_log 分表、HNSW 索引规模化,这些**我都能描述方案**(详见我项目 docs/STUDY-NOTES.md §7),只是 MVP 没做。区别是**有意识收窄 scope vs 没想清楚做不完**——我能讲清楚每个 trade-off 的'为啥不做'和'什么时候必须做'。"

**加分点**:
- reframe "toy" 成 "scope-narrow MVP"
- 主动 reference §7 trade-off 文档
- "scale 是工程任务不是设计问题"——一句话点透

**死刑陷阱**:
- 直接反驳"不是 toy" → ❌ 听上去 defensive
- "我会改" → ❌ 没具体方案
- 装"已经 scale ready" → ❌ 会被深挖戳穿

**追问 fallback**:"那你举一个具体 scale 问题怎么修" → 跳 §7 ⑩ consolidate O(N²) → HNSW 替代

---

### Q17:这套东西跟 ChatGPT Memory 比有啥本质区别?

**骨架**(详见 docs/POSITIONING.md):
> "三个本质区别:
>
> **1. 边界不同**——ChatGPT Memory 是给 chatbot 的通用记忆,我项目专门给 Claude Code 装跨 project 用户画像。**ChatGPT Memory 不能给 Claude Code 用**(协议不通)。
>
> **2. 决策粒度不同**——ChatGPT 闭源,我们不知道它怎么决定记 vs 不记。我项目**决策规则可读可改**:`confidence>=3 AND use_count>=5` 才 promote,LLM 决策都有 reason 留 ops_log。
>
> **3. 责任边界不同**——OpenAI 要给 10 亿 user 找 universal taste,我项目只给程序员(同质用户)。**场景具体 → 判断规则可以收敛**,这是大厂没法做的优势。
>
> 简而言之:**ChatGPT Memory 是'尽量不出错',我项目是'让对的决策被审计'**。两种产品哲学。"

**加分点**:
- "为啥大厂做不了"(不是技术,是产品边界)
- 提 ops_log 审计

**死刑陷阱**:
- 攻击 ChatGPT Memory → ❌ 不用踩
- "我们更智能" → ❌ 不是事实

**追问 fallback**:"如果 OpenAI 给 ChatGPT 加 MCP 支持你这项目还有意义吗?" → 答"有,因为我项目的核心是 Letta read-only primary 这套**架构**,不是 MCP 协议本身。OpenAI 接 MCP 它的 memory 也不会变成 read-only primary"

---

### Q18:你跟 Letta paper 的差异是啥?借鉴了多少,自己加了什么?

**骨架**:
> "**严格借鉴的**:
> - 双 agent 架构(Awake / Sleep)
> - read-only primary(Sleep 是 core 唯一 writer)
> - sleep-time compute pipeline(plan / consolidate / promote / demote / resolve / reflect)
> - 5 个 core memory blocks
> - archival memory + embedding 检索
>
> **我自己加的**:
> - **MCP server 接入** —— Letta paper 没讲怎么对接外部 client,我用 MCP 把 Claude Code 接上
> - **staging snapshot + atomic swap 并发模型** —— Letta paper 没明说并发怎么解,我用 staging 表 + 三对 RENAME 实现 lock-free reading
> - **ops_log 审计层** —— Letta paper 提到要可观测但没明说,我设计了 9 种 op_type + 全文 before/after + reason
> - **信号驱动 promote / demote 阈值** —— `use_count >= 5 AND confidence = 3`,paper 给了思路我定的具体数
>
> **没 follow 的**:
> - Letta 的 `request_heartbeat` 自主链式调用——MVP 不需要 Awake 自主多 step,跳过
> - Letta 的多 user 假设——MVP single-user 写死
>
> **整体**:架构 follow 论文,工程细节自己设计。"

**加分点**:
- 列具体 paper section / 概念名
- 同时讲"借鉴 + 加 + 不做" → 显示真懂论文
- 不夸大原创性

**死刑陷阱**:
- "我自创了大部分" → ❌ 会被追问验证
- "完全照搬" → ❌ 没体现自己工作
- 不知道 Letta paper 内容 → ❌ 没读

**追问 fallback**:"为啥不用 Letta 官方 SDK 而是自实现?" → 答"用 SDK 校招简历变'调包侠',自实现叙事更强;而且 SDK 太重,我项目 scope 收窄到 MCP + 程序员 user,自己实现更合身"

---

## §8 · 章末

### 18 题速查表

| # | 题目 | 关键句 |
|---|---|---|
| Q1 | 30 秒讲项目 | "Letta sleep-time compute + Awake/Sleep + staging swap" |
| Q2 | 为啥不用现成 | "Claude Code 跨 project 是空白" |
| Q3 | 为啥 Python | "AI agent 生态主场 + 差异化补充 Java 实习" |
| Q4 | 完成度 | "核心架构跑通,10 个 trade-off 已知" |
| Q5 | 最难决策 | "Sleep 用 StateGraph 不 ReAct,承认是 agentic workflow" |
| Q6 | read-only primary | "实时不能写 core,Sleep 审完才能 promote" |
| Q7 | Awake/Sleep 分工 | "时间尺度 + 决策粒度不同,合一个反而都做不好" |
| Q8 | staging swap | "lock-free reading + 三对 RENAME + step a 处理新增" |
| Q9 | core/archival 分表 | "字段差异 + 演化方向不同" |
| Q10 | 可观测性 | "ops_log + cycle result dict + last_writer 自检" |
| Q11 | async | "为不阻塞不为并发,刻意没大量用 gather" |
| Q12 | HNSW vs IVF | "高召回 + 读多写少 + 内存不是问题" |
| Q13 | conditional edges | "MVP 不需要,但 DSL 留了演进空间" |
| Q14 | embedding 失败 | "MVP 是 fail-fast,schema 留 defer-write 接口" |
| Q15 | multi-tenant | "按规模分档:schema 隔离 / user_id 列 / 分片" |
| Q16 | toy 项目 | "scope 收窄是有意,scale 是工程任务不是设计" |
| Q17 | vs ChatGPT Memory | "决策规则可读可改 + 边界互补" |
| Q18 | vs Letta paper | "架构 follow + 工程自己设计(MCP/staging/ops_log)" |

### 面试前 1 周准备清单

1. **18 题口头过一遍**——卡壳的标记
2. **§7 trade-off 10 个**——每个能讲"为啥 + 怎么修"
3. **§5 端到端两条流程**——能画白板时序图
4. **§3 架构 4 层 + 6 个 invariants**——能解释每层职责 + invariant 在哪强制
5. **POSITIONING.md**——会被问"为啥不大厂做"

### §8 · 课后思考题(自评准备度)

> 这章是**话术收口**,你要做的不是"想",是"先自评自己哪几道有底 / 哪几道虚"。

#### Q1:从 §1-§7 你最不踏实的 3 个点是啥?

列出来。下次精讲 §8 时我会**重点 cover 你列的弱项**。

#### Q2:18 题里你最自信能讲透的 3 道是哪几道?

也列出来。这些就**别再花时间准备了**,把时间留给弱项。

#### Q3:18 题里**完全没准备过 / 没想过怎么答**的预计有几道?

诚实回答。这是你接下来 1 周必须重点过的清单——**面试前每道至少口头过 1 遍**。

---

# §优化点 Backlog(讨论衍生)

> 面试官问"这项目你还有哪些可改进 / 没做的优化"时,一次答全。这些是**讲解过程中讨论出来的优化点**(区别于 §7 的已知 trade-off,§7 偏"硬伤",这里偏"能做更好但 MVP 没做")。每条标了出处章节,可回查上下文。

| # | 优化点 | 现状 | 怎么改 | 出处 |
|---|---|---|---|---|
| 1 | **embedding 复用** | Day 14 已做:进程内 embedding cache,同文本复用向量 | 后续可加跨进程 cache / provider 级别 metrics | §5.1 讨论补录 |
| 2 | **写异步、读同步** | Day 14 已做:`remember`/`forget` 快速返回 accepted,后台跑;`recall`/`list_memory` 同步 | 后续可加后台失败队列 / 用户可查询写入状态 | §5.1 讨论补录 |
| 3 | **swap 字段级合并** | swap 整行覆盖,丢 cycle 期间 Awake 的 use_count 更新 | 按字段分归属:语义字段(content/confidence)取 staging,统计字段(use_count/last_used)取主表回填 | §4.4 Q3 |
| 4 | **大数据量放弃整表复制** | snapshot 整表复制到 staging,100 万行扛不住 | 改 MVCC 快照读(REPEATABLE READ,不锁不复制)+ 短事务只 apply 改动的少数行 | §4.4 Q1 |
| 5 | **swap 加 lock_timeout** | Day 14 已做:swap transaction 内设置 `lock_timeout=500ms` | 后续可加 retry/backoff 和失败告警 | §4.4 Q2 |
| 6 | **partial index 谓词硬编码**(注意事项) | 谓词若用参数绑定 `$1`,planner 不用 partial index → 白建 | query 硬编码 `WHERE is_deleted=FALSE` + EXPLAIN 验证走 Index Scan | §4.2 Q2 |
| 7 | **use_count 纯读方案**(可选) | 读操作偷偷 UPDATE use_count(违反 CQS,但可接受) | 真要纯读:append 到独立 `access_log` 表,Sleep 聚合时 COUNT | §4.2 Q1 |
| 8 | **可信置信度用 logprobs**(可选) | confidence 由 LLM 正文自报(没校准) | 真要细粒度可信置信度:读 token logprobs + 校准(temperature/Platt scaling) | §4.2 Q3 |
| 9 | **embedding defer-write** | MVP 是 fail-fast:embedding 失败 fact 不入库 | fact 先入库(embedding=NULL)+ 后台 backlog worker 补 | §6.2 |
| 10 | **idle 计时持久化** | 存进程内存变量,重启归零 | 启动时从 ops_log 推算最近活动时间(零写放大) | §6.4 |
| 11 | **ops_log append-only DB 强制** | 应用层自律,DB 没拦 UPDATE/DELETE | PG trigger `BEFORE UPDATE/DELETE RAISE EXCEPTION` 或 `REVOKE` | §4.3 / §7 ① |
| 12 | **resolve 独立 op_type** | Day 14 已做:resolve 写 `sleep_resolve` | 后续可在 inspect 输出里单独分组展示 | §4.3 |
| 13 | **consolidate 升 HNSW 聚类** | O(N²) 朴素聚类,>5000 行超 budget | HNSW top-K 近邻剪枝 / DBSCAN 聚类 | §7 ⑩ |
| 14 | **Awake ReAct 卡死防护** | Day 14 已做:`recursion_limit=8` + LLM `timeout=20,max_retries=1` + 整体 `wait_for=45s` + 写类异步 | 后续可加 p99 latency 监控和 step_count 接近 limit 告警 | §5.2 讨论(Awake ReAct 风险) |

**面试一句话**:"这项目我维护了一个优化 backlog,十几项,从 embedding 复用、写异步读同步,到 swap 字段级合并、大数据量改 MVCC 快照——每项都知道现状、改法和触发条件。MVP 主动没做,是 scope 选择不是没想到。"

---

## 附:Awake 为什么敢用 ReAct,sleep 不敢(讨论补录)

> 出处:§5.2 讲完后的追问"既然能跳过 phase 为啥不用 ReAct + Awake 同步会不会卡死"。

**两种动态性,别混淆**:
- **受控的条件跳过**(sleep plan):在固定 DAG 上**开关节点**,选择空间有限(6 phase × yes/no),顺序焊死,碰不到危险旋钮
- **开放的自由编排**(ReAct):**运行时构造执行路径**,自由度无限,可能乱序 / 重复 / 死循环

**为什么 Awake 能用 ReAct、sleep 不能**:

| | Awake | sleep |
|---|---|---|
| tool 有硬顺序依赖吗 | **没有**(search/insert/load 任意序都安全) | **有**(snapshot 必须先、swap 必须后) |
| 乱跳的最坏后果 | **多花钱**(浪费 LLM/embedding,不毁数据) | **毁数据**(乱序 swap) |
| 所以 | 容忍 ReAct 的乱 | 必须 workflow 焊死顺序 |

→ **核心认知**:ReAct 的"乱"在**安全/幂等操作**上只是经济浪费,在**有硬依赖的操作**上是正确性灾难。Awake 的 5 个 tool 都安全幂等(读无副作用、写单条原子 + 去重),所以乱跳最坏多花钱;sleep 有 snapshot→改→swap 硬依赖,乱 = 毁数据。

**死循环 / 卡死防护**:
- 防死循环:LangGraph `recursion_limit`(默认 25)硬截断 + T=0 收敛 + prompt 引导 finalize → 实际 remember 3 步就完
- **MVP 真实弱点**:默认 recursion_limit=25 + LLM 无显式 timeout + 同步阻塞 → 极端情况卡几十秒(深入分析见下)

---

# §专题 · Awake 同步 ReAct 卡死弱点(深入)

> 这是项目一个**真实、值得专门讨论**的弱点。面试若被问"你这同步架构会不会卡死"或"ReAct 失控怎么办",这一节是完整答案。结构:故障场景 → 根因 → 影响 → 分层修复 → 监控 → 话术。

## 1. 故障场景矩阵(什么情况卡、卡多久)

`run_awake` 当前是 `await agent.ainvoke(...)`——一次 MCP tool call **同步等** ReAct loop 全程跑完。会卡的场景:

| 场景 | 触发条件 | 时长估算 |
|---|---|---|
| **A. LLM 反复跳跃** | LLM 抽风,在 search ↔ load_core 之间来回跳不收敛 | 跳满 recursion_limit=25 步 × ~1.5s/步 ≈ **37 秒** |
| **B. 单次 LLM API 卡住 + 重试** | DeepSeek 端慢/抖动,openai client 默认 `timeout` 很大 + `max_retries=2` | 一步可能 **60s × (1+2 重试) ≈ 180 秒** |
| **C. embedding API 卡住** | 阿里通义慢,`search`/`insert` 里的 `embed_text` 阻塞 | 同 B 量级,每次 embedding 都可能卡 |
| **D. 组合爆炸** | 跳很多步 + 其中几步 API 慢 | **分钟级**,最坏理论上 25 步全慢 = 几分钟 |

→ 关键认知:**recursion_limit 只限"步数",不限"单步时长"**。所以即使步数被限住(场景 A 有上限),**单步 API 卡住(B/C)仍能让总时长爆炸**。两个维度都要管。

## 2. 根因:三个默认值没动 + 同步设计

1. **`recursion_limit` 用 LangGraph 默认 25**——没显式调小;Awake 根本不需要 25 步(remember 3 步、recall 2-3 步)
2. **`ChatOpenAI` 没设 `timeout` / `max_retries`**——用 openai client 默认(timeout 很大 + 重试 2 次),单步可能卡很久
3. **`run_awake` 同步阻塞**——MCP tool call 等 ReAct 全程跑完才返回

→ **三者叠加**:步数没限死 + 单步没限死 + 全程同步等 = 极端情况这次 tool call 卡几十秒到分钟级。

## 3. 影响范围

- 阻塞的是**那一次 MCP tool call**(不是整个服务——asyncio 事件循环还能处理别的请求)
- 但对**调用方 Claude Code**:那次 `remember`/`recall` 迟迟不返回
- 用户感知:取决于 Claude Code 调用时机——**答完用户后台调 → 无感**;**边答边调 → 用户看到卡顿**
- 不会数据损坏(Awake tool 安全幂等),纯粹是**延时/体验**问题

## 4. 分层修复(每层挡一个维度,代码 + 代价)

**第 1 层:限步数**
```python
agent.ainvoke({"messages": [...]}, config={"recursion_limit": 8})
```
- 挡:场景 A(反复跳跃)。8 步对 Awake 绰绰有余,超了 raise `GraphRecursionError`
- 代价:正常任务几乎不可能到 8 步,误截断风险极低

**第 2 层:限单步**
```python
ChatOpenAI(..., timeout=20, max_retries=1)
```
- 挡:场景 B/C(单步 API 卡)。单次 LLM/embedding 最多等 20s,最多重试 1 次
- 代价:慢但合法的请求(比如网络抖动)被砍,需要上层处理失败

**第 3 层:限整体(兜底)**
```python
import asyncio
result = await asyncio.wait_for(_run_awake(command), timeout=45)
```
- 挡:场景 D(组合爆炸)。整个 ReAct loop 45s 没跑完直接砍,返回降级响应
- 代价:接近上限的合法慢请求被砍

**第 4 层:写类异步(根治体验问题)**
```python
# remember / forget 改 fire-and-forget
asyncio.create_task(_run_awake(command))   # 不 await,立刻返回 "已收到"
return {"status": "queued"}
```
- 挡:**从"减少卡时长"升级到"用户根本不等"**(回到 §5.1 写异步讨论)
- 代价:写类失去同步去重 + fact_id 返回 + 失败用户不知道(需后台失败队列)
- 注意:**读类(recall/list_memory)不能异步**,必须同步返回结果

→ **组合策略**:1+2+3 是"防卡死"(限步数+限单步+限整体),4 是"防体验拖累"(写类不让等)。读类靠 1+2+3,写类靠 4。

## 5. 怎么知道卡死发生了(监控)

`run_awake` 返回值里有 `step_count`(=messages 数量),可观测:
- **step_count 接近 recursion_limit** → 说明 LLM 在反复跳跃,该报警 + 看 prompt 是不是有歧义
- **p99 tool 延时监控** → 正常 remember 2.5-4.5s,p99 飙到几十秒说明踩了 B/C/D
- ops_log 的 ts 间隔 → 能反推哪次操作异常慢

→ MVP 没做监控(§7 ⑧ eval/监控缺失),生产化要补。

## 6. 一句话面试话术

> "Awake 同步 ReAct 有真实卡死风险。recursion_limit 只限步数不限单步时长,所以两个维度都要管:**限步数**(recursion_limit=8)+ **限单步**(LLM timeout=20s, max_retries=1)+ **限整体**(asyncio.wait_for 45s 兜底)。这三层防卡死。体验上再加第四层——**写类工具(remember/forget)改 fire-and-forget**,用户根本不等;读类(recall)保持同步因为要拿结果。可观测靠 step_count 接近 limit 报警 + p99 延时监控。MVP 这些没做是 scope 选择,但我清楚弱点在哪、怎么分层补。"

→ 这个回答的价值:**把模糊的"会不会卡死"拆成"步数维度 + 单步维度 + 整体维度"三个可独立处理的问题,每个给代码级方案 + 代价 + 监控**。这是 senior 级的故障分析能力。

---

# §结尾 · 怎么用这份文档

## 复习节奏

| 时机 | 用法 |
|---|---|
| **每天一章** | 8 章 8 天过完一遍 |
| **面试前 3 天** | 重过 §3 / §6 / §7 / §8 |
| **面试前 1 小时** | 看 §1.1(30 秒电梯版)+ §8 速查表 |
| **被问到具体技术** | grep 对应章节(`pgvector` → §2.3 + §6,`staging` → §4.4 + §6.1) |

## 课后思考题清单

每章末尾都有 2-3 道思考题(共 ~25 道),回家做完写答案的话:

- §4.1 Q1-Q2:✅ 已答(见 §4.1 Q&A)
- §4.2 Q1-Q3:✅ 已答 + 点评(CQS 辩护三件套 / partial index 谓词坑 / 小数置信度为啥没意义)
- §4.3 Q1-Q3:待答(append-only DB 强制 / diff 取舍 / retention 演进)
- §4.4 Q1-Q3:✅ 已答 + 点评(大数据改 MVCC快照读+短事务 / 队头阻塞+lock_timeout / 字段级合并)
- §4.5 Q1-Q3:待答(为啥不加 FK / multi-tenant / 性能先栽哪)
- §4.6 Q1-Q2:待答(默写 schema / 30 秒口径)
- §5 Q1-Q3:待答(LLM/embedding 调用次数 / cycle chunk / race)
- §6 Q1-Q3:待答(事务边界 / idle 持久化 / embedding 故障)
- §7 Q1-Q3:待答(自列 3 个伤 / 可执行修复 / reframe 话术)
- §8 Q1-Q3:待答(自评弱项 / 自评强项 / 未准备过的)

**做法**:回家选 3-5 道**最不踏实的**先答,有想法回我,下次面对面我帮你打分 / 纠偏。

## 跟其他文档的关系

| 文档 | 角色 |
|---|---|
| `STUDY-NOTES.md`(本文) | **学习用**——讲透 + 问答,回家细看 |
| `docs/feature-work/2026-06-17-letta-mini-agent-resume-project-plan.md` | **规划用**——11 节项目计划,初次设计时写的 |
| `docs/POSITIONING.md` | **辩护用**——为啥 OpenAI / Anthropic 不做这事 |
| `PLAN.md` / `ARCHITECTURE.md`(项目根) | **产物文档**——给读代码的人看的 |

如果学习中发现这份笔记跟代码不一致 → 以代码为准,这份笔记需要更新(注释 + 提醒下次同步)。
