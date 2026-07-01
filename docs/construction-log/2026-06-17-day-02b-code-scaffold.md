## 施工记录 — 2026-06-17 Day 02b: 中等档代码骨架

> 注:仍是 2026-06-17 同一天。Day 02b = fetch refs(02 上半)完成后,用户拍板"走中等档"+"环境延后" 直接进入代码骨架阶段。

## 本次目标

公司电脑(无环境)情境下,把 **Day 03 + Day 04 的代码骨架** 提前写完:
- 基础设施 6:`config.py` / `db/schema.sql` / `db/models.py` / `llm/client.py` / `mcp_server.py` / `main.py`
- Awake 全套 4:`memory/store.py` / `awake/tools.py` / `awake/agent.py` / 加 `__main__.py`
- 配套:tests 骨架 / `scripts/setup.sh` / `docs/mcp-config-example.json`
- pyproject.toml 修包路径(src layout)

代码**未跑通**——所有验证留待回家装环境。

## 已完成

### 新增文件(15 个)

```
src/dream/__init__.py
src/dream/__main__.py
src/dream/config.py
src/dream/main.py
src/dream/mcp_server.py
src/dream/db/__init__.py
src/dream/db/schema.sql
src/dream/db/models.py
src/dream/llm/__init__.py
src/dream/llm/client.py
src/dream/memory/__init__.py
src/dream/memory/store.py
src/dream/awake/__init__.py
src/dream/awake/tools.py
src/dream/awake/agent.py
src/dream/sleep/__init__.py        (占位,Day 03+ 写)
tests/__init__.py
tests/conftest.py
tests/test_config.py
tests/test_memory_store.py
scripts/setup.sh
docs/mcp-config-example.json
docs/construction-log/2026-06-17-day-02b-code-scaffold.md  (本文件)
```

### 修改

- `pyproject.toml`:`packages = ["src"]` → `packages = ["src/dream"]`(src layout)

## 文件总览(逻辑分层)

| 层 | 文件 | 职责 |
|---|---|---|
| **入口** | `main.py` + `__main__.py` | Starlette app + lifespan,`uv run python -m dream` |
| **MCP** | `mcp_server.py` | `FastMCP` 暴露 4 tools 给 Claude Code |
| **Agent** | `awake/agent.py` | LangGraph `create_react_agent` + system prompt(强约束 read-only primary) |
| **Agent 工具** | `awake/tools.py` | 5 个 `@tool`:load_core / search_archival / insert_archival_fact / get_overview / forget_archival |
| **业务层** | `memory/store.py` | CRUD + 向量检索 + 权限自检 + ops log |
| **数据层** | `db/models.py` + `db/schema.sql` | SQLAlchemy ORM + 建表 SQL,带 `last_writer` 自检字段 |
| **LLM** | `llm/client.py` | DeepSeek(chat) + OpenAI(embedding) 包装,@lru_cache 单例 |
| **配置** | `config.py` | pydantic-settings 读 .env |

## 关键决策 / 发现

### 1. 权限自检的实现位置:**应用层** + **数据库字段双保险**

- 数据库 `core_blocks.last_writer TEXT DEFAULT 'sleep_agent'`(self-check 字段)
- `memory/store.py:write_core_block` 强制 `if actor != "sleep_agent": raise PermissionError`,并在 `memory_ops_log` 记录 `policy_violation`
- Awake 即使 LLM 想动 core,**store 层直接拒绝**

### 2. MCP tool ↔ Awake 内部 tool 不是 1:1

| MCP tool | Awake 内部要做 |
|---|---|
| `remember` | search_archival(去重)→ insert_archival_fact |
| `recall` | load_core / get_overview + search_archival |
| `list_memory` | get_overview |
| `forget` | forget_archival |

理由:MCP 端给 Claude Code 看的是**业务语义**,Awake 内部跑的是 **ReAct 多步**(这才是 agent 性)。

### 3. Awake system prompt 内嵌严格 policy 说明

`awake/agent.py:SYSTEM_PROMPT` 直接告诉 LLM:
> "You may READ core_blocks but you NEVER write them. The Sleep agent will later promote..."

→ Prompt + store-layer guard 双保险。LLM 即使"想错了"调到 write_core_block 也会被拒。

### 4. Tests 分两层

- **Unit tests**(`test_config.py`)— 不依赖 DB / LLM,任何环境都能跑
- **Integration tests**(`test_memory_store.py`)— `@pytest.mark.integration` 标注,默认跳过,`--run-integration` 才跑

回家先跑 unit(`pytest`)确认基础没坏,再跑 integration(`pytest --run-integration`)。

### 5. Sleep agent 没动(Day 03+)

`sleep/__init__.py` 是占位。**Sleep agent prompt 调试必须在真实 LLM 上做**,公司电脑没意义。`main.py:lifespan` 里 scheduler 启动代码写成注释 stub,Day 03+ 解除。

## 未完成 / 阻塞

### Day 03+(必须装环境后)

- [ ] Sleep agent `sleep/agent.py`(LangGraph + reflection prompt)
- [ ] Sleep scheduler `sleep/scheduler.py`(APScheduler idle detection + cron)
- [ ] Staging snapshot + atomic swap 实现
- [ ] Integration tests 实装(test_memory_store 里的 4 个 skip)
- [ ] 跑通 e2e:Claude Code → MCP → Awake → memory → DB
- [ ] Sleep agent prompt 调试(需要 dogfooding 数据)

### 已知 risk(代码没跑过)

1. **LangGraph `create_react_agent` API 实际签名**——skeleton 用 `(llm, tools, prompt=...)`,实际版本可能要 `(model=llm, tools=tools, ...)`,回家 `pip show langgraph` 再 verify
2. **SQLAlchemy 异步 model 用 `Mapped[Optional[str]]`**——可能需要 `Mapped[str | None]`(Python 3.10+ 语法),回家若 mypy/typing 抱怨改即可
3. **pgvector `.cosine_distance(vec)`**——`pgvector.sqlalchemy.Vector` 该方法应该存在,如不存在改 `Vector.cosine_distance(ArchivalFact.embedding, vec)` 函数式调用
4. **MCP `FastMCP(host=..., port=...)` 构造参数**——可能要传到 `mcp.run(host=..., port=...)` 而不是 `FastMCP(...)`,Day 03 实测
5. **`mcp.streamable_http_app()` 返回类型**——是 ASGI app,跟 Starlette `Mount` 应该匹配,但具体路径前缀可能要调

→ 这些都是 1-line 改动,**等环境跑起来报错再改**,不预期会 block。

## 下次接着做(回家路径)

### Step 1. 同步代码到家里电脑

- 公司:`cd ~ && tar -czf dream.tar.gz dream/`
- 微信 / 邮件传给自己
- 家里:`tar -xzf dream.tar.gz -C ~/`

### Step 2. 装环境

```bash
cd ~/dream
bash scripts/setup.sh   # 自动装 PG + pgvector + uv + 建库 + 应用 schema
```

(`setup.sh` 会自己检测,缺啥装啥,幂等)

### Step 3. 填 `.env`

```bash
# scripts/setup.sh 会自动 cp .env.example → .env
# 编辑 .env,填:
#   DEEPSEEK_API_KEY   (你有额度)
#   OPENAI_API_KEY     (注册一个,$1 用一年)
#   DATABASE_URL       (改密码部分)
```

### Step 4. 验证基础

```bash
# 跑 unit tests
uv run pytest

# 启动 service
uv run python -m dream

# 另一个终端测 health
curl http://localhost:8000/health
# → {"status": "ok", "service": "dream"}
```

### Step 5. 接入 Claude Code

(`docs/mcp-config-example.json` 是 draft,Day 03 实测 Claude Code 的 MCP config 真实路径 + 格式后调整)

### Step 6. Day 03 任务

- 跑通 MCP 端到端(Claude Code 调 remember → 数据进 archival)
- 修代码里的 skeleton bug(预计 1-2 hr)
- 开始写 Sleep agent

## 接续指引(给新窗口的 Claude 看)

新窗口接 "继续 dream 项目" 时:

1. 读 `~/dream/README.md`
2. 读 `~/dream/docs/PLAN.md`(尤其 §17 Changelog 确认是 read-only primary 版)
3. 读 `~/dream/docs/DECISIONS.md`(Q1-Q14)
4. 读最新 construction-log(本文件就是最新)
5. 读 `~/dream/docs/research-notes/*` 4 份(避免再 fetch)
6. **特别注意**:本会话写的代码 **未跑通**,首次启动可能要修 1-5 行 import / API 签名
7. 从本文件"下次接着做" Step 1 开始

## Day 02b 数据总结

| 项 | 值 |
|---|---|
| 新增文件数 | 23 |
| 修改文件数 | 1(pyproject.toml) |
| 代码行数 (含注释/空行) | ~1100 |
| 实际可跑 | ❌(无环境) |
| 涵盖功能 | Awake 全套 + 基础设施;Sleep 留空 |
| 累计 dream 文件总数 | 32 |
