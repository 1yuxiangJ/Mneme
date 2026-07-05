# 2026-07-05 Day 24 - Async Write Reliability Backlog

## 背景

用户提出一个消息队列类比问题:

> `remember` 已经返回 accepted,但后台任务如果失败或进程崩溃怎么办?会不会像 MQ 丢消息?

结论:会。这是当前异步写入设计的真实可靠性缺口。

## 当前实现

`remember` / `forget` 当前链路:

```text
Claude Code 调 MCP tool
  -> Mneme 立刻返回 {"status":"accepted","mode":"async"}
  -> asyncio.create_task(_run_awake(command))
  -> 后台 Awake 调 DeepSeek / embedding / DB
  -> 成功后 archival_facts + memory_ops_log 落库
```

`accepted` 当前只表示:

```text
Mneme 进程收到了请求,并创建了后台 task。
```

不表示:

```text
记忆已经成功落库。
```

## 失败模式

后台任务可能因为以下原因丢失:

- DeepSeek 调用失败。
- 阿里 embedding 调用失败。
- DB 写入失败。
- Mneme 进程在后台任务完成前崩溃。
- 机器关机或服务被 kill。

当前只有服务日志能看到部分失败,没有:

- 持久化 pending queue
- retry
- failed status
- status query
- dead-letter queue

因此当前语义接近:

```text
accepted 后 at-most-once-ish
```

## 后续优化方案

引入持久化 job/outbox 表:

```text
memory_write_jobs
```

建议字段:

```sql
id
operation          -- remember / forget
payload_json
status             -- pending / processing / succeeded / failed
attempt_count
last_error
created_at
updated_at
```

目标流程:

```text
remember 请求
  -> DB 事务里插入 memory_write_jobs(status=pending)
  -> 返回 accepted(job_id)
  -> worker 扫 pending
  -> 成功后 status=succeeded
  -> 失败后 attempt_count+1 并重试
  -> 超过阈值 status=failed / dead-letter
  -> 用户或开发者可查询 job 状态
```

这样 `accepted` 语义升级为:

```text
写入意图已持久化,进程崩溃也不会丢。
```

## 已记录到 Mneme

通过 Mneme `remember` 保存了 backlog fact:

```text
Mneme 当前 remember/forget 是异步 fire-and-forget,accepted 只表示后台任务已创建,不保证落库;如果后台任务失败或进程崩溃,记忆可能丢失。后续应引入持久化 memory_write_jobs/outbox 队列、重试、失败状态查询和 dead-letter 机制。
```

Tags:

```text
mneme, backlog, reliability, async-write
```

## 文档同步

- `docs/ARCHITECTURE.md`:补充异步写入可靠性缺口和 job/outbox 方案。
- `docs/STUDY-NOTES.md`:在优化点 backlog 中新增异步写入持久化队列项。
