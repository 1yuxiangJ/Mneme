# 施工记录 — 2026-07-01 Day 05: 本地集成测试硬化

## 本次目标

接 Day 04 的 "回家装环境 + 修 P0/P1 risk" 继续做。重点不是加新功能,而是把原来 skip 的数据库集成测试补实,用真实 PostgreSQL + pgvector 验证 Memory Store 和 Sleep staging 的关键行为。

## 已完成

- [x] `greenlet` 加入运行依赖,修复 SQLAlchemy async session 启动失败。
- [x] 补实 `tests/test_memory_store.py`:插入/搜索 archival、Awake 禁写 core、Sleep 写 core、soft delete、mark used 不写 log。
- [x] 补实 `tests/test_sleep_staging.py`:snapshot、atomic swap、Awake cycle 中新增 archival merge、cleanup staging。
- [x] 新增 P0-3 覆盖:验证 `find_consolidation_clusters()` 的 pgvector raw SQL 参数绑定。
- [x] 修复 ORM timezone 映射:`TIMESTAMPTZ` 对应 `DateTime(timezone=True)`。
- [x] 修复 `atomic_swap` 后 `archival_facts.id` 自增 default 丢失的问题。
- [x] 修复 Sleep consolidation raw SQL:显式 `CAST(:emb AS vector)`,并正确处理 DB 返回的 vector 字面量。
- [x] 本地 `.env` 已填入 DeepSeek + DashScope key,不写入文档明文。
- [x] 修复 DashScope embedding 兼容问题:关闭 LangChain token-array 输入,保持原始 string。
- [x] 真实 provider smoke test 通过:DashScope 返回 1024 维 embedding,DeepSeek 返回预期 JSON。
- [x] 真实 memory smoke test 通过:插入临时 fact → 向量搜索命中 → soft-delete 清理。
- [x] Awake ReAct `list_memory` 通过真实 DeepSeek 调用和本地工具调用。
- [x] 新增成本保护:`SLEEP_SCHEDULER_ENABLED=false` 默认关闭自动 idle/cron Sleep。
- [x] 本地服务启动通过,`/health` 返回 ok。
- [x] 修复 Starlette/FastMCP 路由挂载:`/mcp` 已能命中 FastMCP streamable HTTP route。
- [x] Claude Code 项目级 MCP approval 完成。
- [x] 定位 Claude Code 连接失败根因:坏的 `HTTP_PROXY/HTTPS_PROXY` 指向本地 10910,需绕过或清理。
- [x] 新增 `scripts/claude-mneme.sh`,自动清代理并设置 `NO_PROXY`。
- [x] Claude Code 侧真实 MCP 调用通过:`list_memory` / `remember` / `recall`。
- [x] 清理 `ruff` lint,当前 `ruff check` 通过。

## 关键发现

### 1. SQLAlchemy async 漏了 `greenlet`

项目用了 `create_async_engine` / `AsyncSession`,但依赖里没有声明 `greenlet`。首次跑集成测试时所有 DB fixture 都在 session 初始化处失败。已在 `pyproject.toml` 补上。

### 2. `atomic_swap` 会破坏后续 INSERT

`CREATE TABLE ... LIKE ... INCLUDING ALL` 生成 staging 表后,swap 过来的新主表可能没有 `archival_facts.id` 的 sequence default。结果是 Sleep cycle 跑完后,Awake 再 `remember` 会出现 `id = NULL` 插入失败。

修复:创建 `archival_facts_staging` 后显式设置:

```sql
ALTER TABLE archival_facts_staging
ALTER COLUMN id SET DEFAULT nextval('archival_facts_id_seq'::regclass)
```

### 3. pgvector raw SQL 问题确实存在

`row_i.embedding` 从 raw SQL 读出来时可能是 pgvector 字面量字符串。原代码 `list(row_i.embedding)` 会把字符串拆成字符列表,导致 pgvector 解析失败。

修复:保留字符串字面量;非字符串时再拼成 `[x,y,z]`;SQL 里使用 `CAST(:emb AS vector)`。

### 4. DashScope embedding 不能吃 LangChain token array

`OpenAIEmbeddings` 默认 `check_embedding_ctx_length=True`,会把输入文本 token 化后再发给 OpenAI embedding API。DashScope 的 OpenAI-compatible embedding endpoint 在当前模型下要求 `input` 是 string 或 string list,不接受 token id array。

修复:`get_embedder()` 设置 `check_embedding_ctx_length=False`,让请求保持原始字符串。

### 5. 自动 Sleep 默认关闭

服务启动时不再默认注册 idle/cron scheduler。需要自动做梦时再显式设置:

```env
SLEEP_SCHEDULER_ENABLED=true
```

这样开发和 demo 准备阶段不会因为服务常驻 30 分钟自动消耗 LLM token。

### 6. FastMCP 不应该二次 mount 到 `/mcp`

`mcp.streamable_http_app()` 自己已经包含 `/mcp` route。主 app 原来再 `Mount("/mcp", ...)`,真实路径变成 `/mcp/mcp`,导致 Claude Code health check 失败。

修复:主 app 将 FastMCP 子 app mount 到 `/`,保留 `Route("/health", ...)` 在前面。

### 7. Claude Code 连接本机 MCP 会被坏代理影响

当前 shell 环境里有:

```text
HTTP_PROXY=http://127.0.0.1:10910
HTTPS_PROXY=http://127.0.0.1:10910
```

如果 10910 没有代理进程,Claude Code 会连不上自己的 API,也连不上本机 Mneme MCP。`NO_PROXY=127.0.0.1,localhost` 可以解决 MCP 连接;更稳妥是用项目脚本:

```bash
scripts/claude-mneme.sh
scripts/claude-mneme.sh mcp list
```

## 验证结果

```bash
/Users/mac/.local/bin/uv run pytest
# 2 passed, 10 skipped

/Users/mac/.local/bin/uv run pytest --run-integration
# 12 passed

/Users/mac/.local/bin/uv run ruff check
# All checks passed!

/Users/mac/.local/bin/uv run python -c "from mneme.awake.agent import get_awake_agent; get_awake_agent(); from mneme.sleep.agent import get_sleep_graph; get_sleep_graph(); print('agents ok')"
# agents ok

/Users/mac/.local/bin/uv run python -m mneme
# /health -> {"status":"ok","service":"mneme"}

scripts/claude-mneme.sh mcp list
# mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected
```

## 未完成

- [ ] 真实 MCP `forget` 还没从 Claude Code 侧跑。
- [ ] `uv run mypy src` 仍有 41 个 strict 类型错误,主要是 agent/MCP 入口历史类型标注债。
- [ ] 还没 dogfood 积累真实 memory,也还没调 prompt。

## 下次接着做

1. 用 Claude Code 侧真实 MCP 工具跑 `forget`。
2. 手动触发一次 Sleep cycle,观察 `memory_ops_log` 和 staging swap 后的主表结果。
3. 再决定是否先修 mypy strict,还是先做 demo dogfooding。
