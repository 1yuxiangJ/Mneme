# 2026-07-04 Day 14 - Agent 体验与可观测性加固

## 背景

用户要求执行前面定下的 5 个施工计划:

1. Awake ReAct 卡死防护
2. 写异步、读同步
3. embedding 复用
4. resolve 独立 `sleep_resolve` op_type
5. swap 加 `lock_timeout`

## 本次代码改动

### 1. Awake ReAct 卡死防护

- 新增配置:
  - `AWAKE_REACT_RECURSION_LIMIT=8`
  - `AWAKE_LLM_TIMEOUT_SECONDS=20`
  - `AWAKE_LLM_MAX_RETRIES=1`
  - `AWAKE_OVERALL_TIMEOUT_SECONDS=45`
- `awake/agent.py`:
  - `create_react_agent` 使用带 timeout / max_retries 的 ChatOpenAI
  - `agent.ainvoke(..., config={"recursion_limit": ...})`
  - 外层用 `asyncio.wait_for` 做整体超时
  - 超时返回 `status="timeout"` 而不是让调用方一直等

### 2. 写异步、读同步

- `mcp_server.py`:
  - `remember` / `forget` 改为快速返回 `{status: "accepted", mode: "async"}`
  - 后台 `asyncio.create_task` 执行 Awake ReAct
  - 后台失败写服务日志
  - `recall` / `list_memory` 保持同步,因为它们的结果会影响当前回答

代价:写入是最终一致。刚 `remember` 后立刻 `recall` 可能短暂查不到。

### 3. embedding 复用

- `llm/client.py`:
  - 新增进程内 LRU cache
  - `embed_text("same text")` 命中 cache 时不再调 embedding API
  - 新增 `EMBEDDING_CACHE_SIZE=256`

直接收益:`remember` 链路里 search 去重和 insert 入库对同一文本的 embedding 可复用。

### 4. resolve 独立 op_type

- `memory/store.py` 的 `OpType` 增加 `sleep_resolve`
- `sleep/tools.py::apply_resolutions` 从 `sleep_consolidate` 改为 `sleep_resolve`
- `db/schema.sql` 注释同步

收益:审计日志可以区分"合并重复事实"和"解决 core 冲突"。

### 5. swap 加 lock_timeout

- 新增 `SLEEP_SWAP_LOCK_TIMEOUT_MS=500`
- `sleep/staging.py::atomic_swap` 在 transaction 开头执行:
  `SELECT set_config('lock_timeout', '500ms', true)`

收益:swap 需要拿表锁时,如果撞上慢查询或长事务,快速失败而不是阻塞在线读写。

## 测试

新增/更新测试:

- `tests/test_awake_agent.py`
- `tests/test_mcp_async_writes.py`
- `tests/test_llm_client.py`
- `tests/test_sleep_staging.py`
- `tests/test_sleep_staging_unit.py`

已先观察到红灯:

- Awake 没有 `settings` / recursion limit / timeout 配置
- `remember` 同步等待后台操作导致测试卡住

实现后局部测试通过:

```bash
/Users/mac/.local/bin/uv run pytest \
  tests/test_awake_agent.py \
  tests/test_mcp_async_writes.py \
  tests/test_llm_client.py \
  tests/test_sleep_staging_unit.py \
  tests/test_sleep_staging.py \
  --run-integration
```

结果:14 passed。

## 文档

- `.env.example` 增加新配置项
- `docs/ARCHITECTURE.md` 同步:
  - 写异步、读同步
  - Awake 防卡死参数
  - embedding cache
  - `sleep_resolve`
  - swap `lock_timeout`
- `docs/STUDY-NOTES.md` 的优化 backlog 标注 Day 14 已完成项
