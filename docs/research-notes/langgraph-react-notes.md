# LangGraph ReAct Agent 笔记

> 来源:
> - WebFetch `https://docs.langchain.com/oss/python/langgraph/quickstart`(2026-06-17,**部分**)
> - 标 ⚠️ 的部分**Day 02 跑通后再 verify**(LangGraph API 演进快)
>
> LangGraph 提供 **两套 agent API**:
> - **Prebuilt**(简单):`create_react_agent`,一行起 ReAct
> - **Graph API**(灵活):`StateGraph` 自己拼,适合非标准 loop

## 1. 安装

```bash
pip install -U langgraph langchain langchain-openai
```

## 2. mneme 推荐:Prebuilt `create_react_agent`(Awake Agent 用)

### 2.1 完整模板(skeleton,Day 02 验证)

```python
import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent


@tool
def remember(content: str, tags: list[str] | None = None, confidence: int = 2) -> dict:
    """Store a fact about the user (preferences, habits, lessons learned).
    Only call for cross-project user-level facts."""
    # actual implementation calls memory store
    return {"status": "ok", "fact_id": "..."}


@tool
def recall(query: str, limit: int = 5) -> dict:
    """Semantic search over stored memory."""
    return {"results": [...]}


tools = [remember, recall]  # plus list_memory / forget


# === DeepSeek via OpenAI-compatible base_url ===
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)


# === System prompt 教 LLM 何时调 remember/recall ===
SYSTEM_PROMPT = """\
You are mneme's Awake agent. You receive remember/recall requests from Claude Code via MCP.

When handling `remember`:
1. Search existing memory first (call recall internally if needed).
2. Decide: merge into core block, insert as new archival, or skip if duplicate.
3. Execute and return summary.

When handling `recall`:
1. Search core_blocks + archival_facts.
2. Return ranked top results.

Only call recall/remember for facts about the user themselves (preferences, habits, cross-project lessons). Project-specific facts belong in CLAUDE.md."""


agent = create_react_agent(
    llm,
    tools,
    prompt=SYSTEM_PROMPT,
)


# === 调用 ===
result = agent.invoke({
    "messages": [
        ("user", "remember that I prefer 4-space indent")
    ]
})

print(result["messages"][-1].content)
```

### 2.2 Stream 模式

```python
async for event in agent.astream({"messages": [...]}, stream_mode="values"):
    print(event["messages"][-1])
```

## 3. Graph API(Sleep Agent 用,更灵活)

Sleep agent 内部要做多阶段(consolidate → promote → demote → reflect),可能用 `StateGraph` 更顺。

### 3.1 已确认的 imports(从官方 quickstart fetch 来)

```python
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, SystemMessage, ToolMessage, HumanMessage
from typing_extensions import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END
```

### 3.2 模板(skeleton,Day 02 验证)

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


class SleepState(TypedDict):
    snapshot: dict
    consolidated: list
    promoted: list
    demoted: list
    reflection: str


def load_snapshot(state: SleepState) -> SleepState:
    # snapshot current memory
    ...

def consolidate(state: SleepState) -> SleepState:
    # LLM decides merges
    ...

def promote(state: SleepState) -> SleepState:
    ...

def demote(state: SleepState) -> SleepState:
    ...

def reflect(state: SleepState) -> SleepState:
    ...

def atomic_swap(state: SleepState) -> SleepState:
    ...


graph = StateGraph(SleepState)
graph.add_node("load", load_snapshot)
graph.add_node("consolidate", consolidate)
graph.add_node("promote", promote)
graph.add_node("demote", demote)
graph.add_node("reflect", reflect)
graph.add_node("swap", atomic_swap)

graph.add_edge(START, "load")
graph.add_edge("load", "consolidate")
graph.add_edge("consolidate", "promote")
graph.add_edge("promote", "demote")
graph.add_edge("demote", "reflect")
graph.add_edge("reflect", "swap")
graph.add_edge("swap", END)

sleep_agent = graph.compile()
```

⚠️ **每个 node 内部仍是 LLM driven**(LLM 决定哪些 merge / promote),**不是 cron + SQL update**。这是项目灵魂,必须保住。

## 4. ⚠️ LangGraph 0.2 vs 0.3 vs 后续版本

- LangGraph API 变化较快(2025 中 0.2 → 0.3 重命名了 ChatOpenAI 包路径,`langchain.chat_models.init_chat_model` 是新推荐入口)
- **mneme MVP**:固定一个版本(`pyproject.toml` 已声明 `langgraph>=0.2`),Day 02 跑通后**锁版本**
- 如果 API 不一致,以 `pip show langgraph` 输出的实际版本对应的官网文档为准

## 5. 用 DeepSeek 的 3 种姿势

| 姿势 | 代码 | 推荐度 |
|---|---|---|
| **A. `ChatOpenAI` 直接传 base_url** | `ChatOpenAI(model="deepseek-chat", base_url="...", api_key=...)` | ⭐⭐⭐ MVP 最稳 |
| **B. `init_chat_model`** | `init_chat_model("openai:deepseek-chat", api_base="...")` | ⭐⭐ 新写法,可能版本依赖 |
| **C. 自建 client wrapper** | 自己封装 retry/cache | ⭐ Day 02+ 再优化 |

→ **MVP 用 A**,简单稳定。

## 6. mneme MVP 用 LangGraph 的边界

| Awake Agent | 用 `create_react_agent`(prebuilt) | Day 02-04 实现 |
|---|---|---|
| Sleep Agent | 用 `StateGraph`(Graph API) | Day 05 实现 |
| 状态持久化 | LangGraph 自带 checkpointer(Postgres) | MVP 可选,简化版用内存 checkpointer |
| 并发安全 | 由 mneme service 层管(staging swap),不是 LangGraph 责任 | Day 06 |

---

## 7. 待 Day 02 验证清单

- [ ] `pip install langgraph` 实际装到哪个版本
- [ ] `create_react_agent` API 签名是否跟 skeleton 一致
- [ ] DeepSeek tool calling 跟 LangGraph 配合是否顺(JSON schema 严格度)
- [ ] StateGraph 是否需要 checkpointer 才能 run(可能要)
- [ ] async vs sync invoke 推荐哪个(FastAPI 用 async)

---

## 8. 参考链接(Day 02 起需要时查)

- 官方 quickstart:`https://docs.langchain.com/oss/python/langgraph/quickstart`
- GitHub examples:`https://github.com/langchain-ai/langgraph/tree/main/examples`
- API reference:`https://reference.langchain.com/python/langgraph`
