# 2026-07-05 Day 29 - Durable Write Queue for Remember / Forget

## 背景

用户指出:

> 如果 remember 的时候消息丢了怎么办? forget 会不会也有同样问题?

排查当前代码后确认:

- `remember` 走 `_schedule_awake_write()`。
- `forget` 也走 `_schedule_awake_write()`。
- 旧实现用 `asyncio.create_task(_run_awake(command))` 创建内存后台任务。

因此旧语义是:

```text
MCP 返回 accepted
→ 后台任务仍在 Python 内存中
→ 如果 Mneme 进程在任务完成前崩溃
→ remember / forget 可能丢失
```

同步写可以消除这个窗口,但会把 Awake LLM + embedding + DB 写入延迟直接压到
Claude Code 当前响应上,用户明确否定了同步写方案。

## 决策

采用 PostgreSQL-backed durable queue:

```text
remember / forget
→ INSERT memory_write_jobs
→ COMMIT 成功后返回 accepted + job_id
→ memory worker 异步 claim job
→ worker 复用 Awake agent 执行原 command
→ succeeded / failed
```

暂不引入 Kafka / Redis Stream,原因:

- 当前写入瓶颈在 LLM / embedding,不是消息吞吐。
- 项目已经依赖 PostgreSQL,不用新增基础设施。
- DataGrip 可以直接检查 job 状态,适合当前学习和 demo。

## Trade Off

获得:

- `accepted` 前写入意图已经持久化。
- 进程崩溃不会丢掉 pending job。
- 保留异步体验,不阻塞 Claude Code 当前回答。
- worker 复用 Awake,不用重写 remember / forget 业务逻辑。

代价:

- 仍然是最终一致性:刚 remember 后立刻 recall 可能查不到。
- 多一张 `memory_write_jobs` 表和一个后台 worker。
- `forget` 继续走 Awake,会有一次不必要但统一的 LLM 调用。
- 完全相同请求用 `dedupe_key` 防重复,语义相似重复仍靠 Awake 去重。

## 代码改动

- `src/mneme/db/schema.sql`
  - 新增 `memory_write_jobs` 表。
  - 新增 `idx_memory_write_jobs_claim` 索引。
- `src/mneme/db/models.py`
  - 新增 `MemoryWriteJob` ORM model。
- `src/mneme/memory/jobs.py`
  - 新增 `enqueue_awake_write()`。
  - 新增 `claim_next_write_job()`。
  - 新增 `mark_write_job_succeeded()` / `mark_write_job_failed()`。
  - 新增 stale running job 恢复。
- `src/mneme/memory/worker.py`
  - 新增 `process_one_job()` / `drain_available_jobs()` / `worker_loop()`。
  - 失败按 5s / 30s / 120s 重试,超过 `max_attempts` 后 `failed`。
- `src/mneme/mcp_server.py`
  - `remember` / `forget` 改为 durable enqueue。
  - 返回 `mode="durable_async"` 和 `job_id`。
- `src/mneme/main.py`
  - lifespan 启动/停止 memory worker。
- `src/mneme/config.py`
  - 新增 worker 配置项。
- `scripts/inspect_memory_jobs.py`
  - 查看 job 状态。
- `scripts/drain_memory_jobs.py`
  - 手动 drain pending job。

## 文档改动

- `docs/ARCHITECTURE.md`
  - 更新 `remember` / `forget` tool 语义。
  - 更新 remember sequence diagram。
  - 新增 `memory_write_jobs` 数据表说明。
  - 术语表新增 worker / durable queue。
- `docs/STUDY-NOTES.md`
  - 新增 durable queue 学习笔记和面试话术。

## 验证记录

先补红灯测试:

```bash
/Users/mac/.local/bin/uv run pytest \
  tests/test_mcp_async_writes.py tests/test_memory_write_worker.py
```

旧实现失败:

```text
ImportError: cannot import name 'worker' from 'mneme.memory'
```

实现后通过:

```text
7 passed
```

静态检查:

```bash
/Users/mac/.local/bin/uv run ruff check src tests scripts
/Users/mac/.local/bin/uv run mypy src scripts
```

结果:

```text
All checks passed!
Success: no issues found in 35 source files
```

真实数据库验证:

```bash
/opt/homebrew/opt/postgresql@17/bin/psql mneme -f src/mneme/db/schema.sql
```

确认 `memory_write_jobs` 已创建,字段包括:

```text
id, operation, command, payload, dedupe_key, status, attempt_count,
max_attempts, available_at, locked_at, completed_at, last_error,
result, created_at, updated_at
```

不调用 LLM 的队列自检通过:

```text
enqueue_awake_write -> claim_next_write_job -> mark_write_job_succeeded
```

输出:

```text
{'job_id': 1, 'claimed': 1, 'status': 'ok'}
```

随后删除测试 job,`scripts/inspect_memory_jobs.py --limit 5` 返回空列表。

服务重启后日志确认:

```text
memory write worker starting
Uvicorn running on http://127.0.0.1:8000
```

健康检查:

```text
{"status":"ok","service":"mneme"}
```
