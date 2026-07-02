# Code Review — 自查报告

> 这是 Day 04 在“还没跑过本地环境”时写的历史自查报告。Day 05-07 已经
> 按这里的 P0/P1 风险完成真实 PostgreSQL/pgvector 集成测试、真实 MCP smoke、
> 手动 Sleep smoke,并把 `mypy strict` 清到 0。

当前质量门:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```

当前结果:

```text
ruff: All checks passed
mypy: Success, no issues found in 22 source files
pytest: 18 passed, 1 warning
```

下面保留原始自查内容,用于说明当时识别了哪些风险,以及后续是怎么逐项验证/修复的。

## 评级

| 级 | 含义 | 数量 |
|---|---|---|
| 🔴 P0 | 几乎肯定 fail,必须先修 | 3 |
| 🟡 P1 | 高概率运行时报错 | 6 |
| 🟢 P2 | 可能 fail / 改善点,跑起来再看 | 6 |

**总计 15 个 known risk**,每个都标了文件 + 大致行号 + 修复建议。

---

## 🔴 P0(必须先修)

### P0-1. `awake/tools.py` @tool 返回值含 datetime

**文件**:`src/mneme/awake/tools.py` 全部 5 个 `@tool`
**问题**:`langchain_core.tools.@tool` 会 stringify 返回值给 LLM。返回 dict 里含 datetime(`b.updated_at`)会爆。
**修法**:返回前确保所有 datetime → `.isoformat()`,所有 `Decimal` → `float`,所有自定义 dataclass → `.__dict__` 或显式转 dict。

```python
# 错(目前):
return {"blocks": [{"label": b.label, "updated_at": b.updated_at, ...}]}

# 对:
return {"blocks": [{"label": b.label, "updated_at": b.updated_at.isoformat() if b.updated_at else None, ...}]}
```

或者全部 wrap 用 `json.dumps(..., default=str)` 然后 `json.loads` 回 dict。

### P0-2. `memory/store.py` pgvector `.cosine_distance()` 方法名

**文件**:`src/mneme/memory/store.py:semantic_search_archival`
**问题**:`ArchivalFact.embedding.cosine_distance(vec)` 是 `pgvector.sqlalchemy.Vector` 的实例方法。Verify 实际 API:

```python
# 可能写法:
ArchivalFact.embedding.cosine_distance(vec)           # 我目前写的
ArchivalFact.embedding.op('<=>')(vec)                  # raw operator
func.cosine_distance(ArchivalFact.embedding, vec)      # 函数式
```

**修法**:回家 `python -c "from pgvector.sqlalchemy import Vector; help(Vector)"` 看真实 API,改对应一行。

### P0-3. `sleep/tools.py` pgvector raw SQL `<=>` 参数绑定

**文件**:`src/mneme/sleep/tools.py:find_consolidation_clusters`
**问题**:

```python
"... embedding <=> :emb AS dist ..."
{"emb": str(list(row_i.embedding))}
```

`str(list(...))` 输出 `"[0.1, 0.2, ...]"`——pgvector 接受 `'[1,2,3]'::vector` 字面量,但**不一定接受**普通 string 参数。可能需要显式 cast。

**修法**:试两种:
```python
# A. 用 sqlalchemy 的 bindparam 显式 cast:
from sqlalchemy import bindparam
stmt = text("... embedding <=> CAST(:emb AS vector) AS dist ...")
stmt = stmt.bindparams(bindparam("emb", str(list(...))))

# B. 让 pgvector-sqlalchemy 自动处理:用 ORM column 而非 raw SQL
# (重写整个查询)
```

---

## 🟡 P1(高概率 fail)

### P1-4. `awake/agent.py` `create_react_agent` 签名

**文件**:`src/mneme/awake/agent.py:get_awake_agent`
**问题**:我写 `create_react_agent(llm, AWAKE_TOOLS, prompt=SYSTEM_PROMPT)`。LangGraph 不同 minor 版本签名可能是 `create_react_agent(model=llm, tools=tools, state_modifier=...)`。

**修法**:`pip show langgraph` 看实际版本,看官方 example:
```bash
uv run python -c "from langgraph.prebuilt import create_react_agent; help(create_react_agent)"
```

### P1-5. `sleep/agent.py` LangGraph StateGraph API

**文件**:`src/mneme/sleep/agent.py:build_sleep_graph`
**问题**:`g = StateGraph(SleepState); g.add_node(...); g.add_edge(...)`。
LangGraph 0.2/0.3 之间 API 微调,可能要 `g.set_entry_point("snapshot")` 而不是 `g.add_edge(START, "snapshot")`,或者 `compile()` 参数不同。

**修法**:运行时报错,看错误信息按版本调。可能需要:
```python
# 旧版:
g.set_entry_point("snapshot")
g.set_finish_point("swap")
# 新版:
g.add_edge(START, "snapshot")
g.add_edge("swap", END)
```

### P1-6. SQLAlchemy `Mapped[Optional[X]]` for `ARRAY[Text]`

**文件**:`src/mneme/db/models.py:ArchivalFact.tags`
**问题**:`Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))`。SQLAlchemy 2.0 严格,可能要 `Mapped[list[str] | None]` 显式 union(Python 3.10+ 语法)。

**修法**:运行报错改成 union 语法。

### P1-7. `mcp_server.py` `FastMCP(host=, port=)` 构造参数

**文件**:`src/mneme/mcp_server.py`
**问题**:`FastMCP("mneme", host=..., port=...)` —— `FastMCP` 构造器很可能**不接受** host/port(那些是 `mcp.run()` 的参数)。

**修法**:
```python
# 错(目前):
mcp = FastMCP("mneme", host=..., port=...)

# 对:
mcp = FastMCP("mneme")
# host/port 由 uvicorn 控制(main.py 里),或者 mcp.run(host=, port=)
```

### P1-8. `main.py` Starlette Mount + `streamable_http_app()`

**文件**:`src/mneme/main.py`
**问题**:`Mount(settings.mcp_server_path, app=mcp.streamable_http_app())`。

可能问题:
- MCP SDK 默认 expect mount 在 `/`,加 prefix 可能让 path matching 错
- `streamable_http_app()` 可能要传参数(session_manager / endpoint)

**修法**:试两种:
```python
# A. 单独跑 MCP(不挂在 Starlette 下):
mcp.run(transport="streamable-http", host=..., port=...)
# B. 挂根:
Mount("/", app=mcp.streamable_http_app())
```

### P1-9. `sleep/scheduler.py` AsyncIOScheduler 启动时机

**文件**:`src/mneme/sleep/scheduler.py:start_sleep_scheduler`
**问题**:`AsyncIOScheduler().start()` 需要 event loop 已在运行。Starlette lifespan 的 `async with` 内**应该**有 loop,但某些 APScheduler 版本要 `start(paused=False, ...)`,或要先 attach event loop。

**修法**:运行报错改 `start()` 参数或在 lifespan 里 `await asyncio.sleep(0)` 让 loop 暖一下再 start。

---

## 🟢 P2(改善点)

### P2-10. `sleep/tools.py:find_consolidation_clusters` O(N²)

**已注释**:"Naive O(N²) for MVP. For MVP archival sizes (<1000), this is fine."

但 `visited` 累积大了 `id != ALL(:visited)` 慢。Day 05+ 用 temp table。

### P2-11. `sleep/staging.py:cleanup_staging` 不在 transaction

DROP 单 statement auto-commit,异常时只 partial drop。Day 05+ 包 transaction。

### P2-12. `datetime.utcnow()` Python 3.12+ deprecated

**文件**:`memory/store.py:write_core_block`, `sleep/agent.py:run_sleep_cycle`
**修法**:全局 search + replace `datetime.utcnow()` → `datetime.now(timezone.utc)`(可在公司电脑现在改)。

```bash
# 一次性 grep + sed:
grep -rn "datetime.utcnow" src/
```

### P2-13. `@tool` docstring 太长

**文件**:`src/mneme/awake/tools.py`
LangChain `@tool` 把 docstring 当 description 给 LLM。冗长 docstring 占 prompt context,可能影响 LLM 注意力。Day 05+ 调优时简化。

### P2-14. 缺 `logs/` 目录

**问题**:`.env.example` 写 `LOG_FILE=logs/mneme.log`,但 `logs/` 目录不存在;`main.py` 当前用 `basicConfig` 输出到 stderr,所以不会爆。**但**未来切 FileHandler 时会爆。

**修法**:
- 加 `logs/` 到 `setup.sh`(`mkdir -p logs`)
- 或 `main.py` 启动时 `os.makedirs("logs", exist_ok=True)`
- 加 `logs/` 到 `.gitignore`(已经有 `*.log` 和 `logs/`)

### P2-15. `mcp_server.py` 每个 tool 都走 ReAct = 延迟 + 成本

**问题**:`list_memory()` 本质只是 SQL,但要 round-trip LLM。每个 MCP 调用 1-3 秒 + 几百 token。

**Trade-off**:
- ✅ 维持 agent 性(LLM-driven)
- ❌ 延迟 + 成本

**Day 05+ 改进**:给 `list_memory` 加 fast path(直接调 `store.get_memory_overview`,不走 LLM)。Awake agent system prompt 加一行 "for list_memory, return store overview directly"。

---

## ✅ 已审一遍 OK 的

- ✅ 权限自检三道保险逻辑闭环(prompt + PermissionError + DB last_writer)
- ✅ staging swap 三步 rename 在单 transaction 内正确(PG 支持 ALTER TABLE RENAME in tx)
- ✅ 异常 cleanup_staging 兜底
- ✅ session_factory + dispose_engine lifespan 配合 OK
- ✅ APScheduler single-flight + coalesce 配置正确
- ✅ memory_ops_log 写在 same session,跟主操作同 transaction
- ✅ `_safe_parse_json` 容忍 LLM code fence
- ✅ deadline budget 每 phase check
- ✅ insert_archival_fact 不直接写 core(read-only primary 在 store 层强制)
- ✅ MCP `streamable-http` transport 选择正确(vs stdio,后者要拉 DB 连接)

---

## 修复优先级 / 时间预算

回家跑起来,按这个顺序修(预计总时长 1-3 hr):

| 优先级 | 修啥 | 验证 | 预计时间 |
|---|---|---|---|
| 第 1 | P1-4 + P1-5(LangGraph 签名 + StateGraph API) | `uv run python -c "from mneme.awake.agent import get_awake_agent; get_awake_agent()"` | 15 min |
| 第 2 | P1-7(FastMCP 参数) | service 起得来 | 5 min |
| 第 3 | P1-8(Starlette Mount) | curl health + MCP endpoint 通 | 10 min |
| 第 4 | P0-2 + P0-3(pgvector 距离 / raw SQL) | 用 fake 数据跑一次 recall | 30 min |
| 第 5 | P0-1(datetime serialize) | recall 返回值合法 JSON | 15 min |
| 第 6 | P1-6 + P1-9 | 全部 import 通 + scheduler 起得来 | 15 min |
| 第 7 | 跑 unit tests | `uv run pytest` | 5 min |
| 第 8 | 强制触发 sleep cycle 看 e2e | `uv run python -c "import asyncio; from mneme.sleep.agent import *; asyncio.run(run_sleep_cycle())"` | 30 min |
| 第 9 | P2 改善 | 看心情 | 1+ hr |

---

## 🔧 公司电脑能现在改的(不需要环境)

只有 **P2-12**(datetime.utcnow → datetime.now(timezone.utc))。其他全部依赖跑代码才能验证。

要不要现在顺手改 P2-12?Day 04 范围内的事。

---

## 总评

代码**未跑过**,但已主动审一遍标出 15 个潜在 risk。这份文档回家**先读 30 分钟**再开跑,能省 1-2 小时盲调时间。

P0/P1 三类 risk 都是 1-line 级别修法,**结构没问题**,只是接口细节匹配上的 spot fixes。
