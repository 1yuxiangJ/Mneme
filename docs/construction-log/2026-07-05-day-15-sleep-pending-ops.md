# 2026-07-05 Day 15 - Sleep pending ops 审计语义修正

## 背景

用户指出一个事务边界问题:

- Sleep phase 内部的"改 staging + 写日志"确实是同一个事务。
- 但整个 Sleep cycle 不是一个大事务。
- 如果前面 phase 已经写了 `memory_ops_log`,最后 `atomic_swap` 因为
  `lock_timeout` 失败,主表不会更新,但日志里会留下本轮未生效的 Sleep 操作。

这不是主表数据损坏,但会造成审计语义歧义。

## 方案选择

讨论过三个方案:

1. `sleep_cycles + cycle_id`:审计最完整,但表和查询都更重。
2. `memory_ops_log_staging`:日志也 staged,但多一张临时表。
3. 内存 `pending_ops`:Sleep phase 只生成日志草稿,最后 swap 成功时同事务 flush。

本次采用方案 3。

理由:

- 不新增表结构。
- 失败 Sleep cycle 的尝试日志可以丢弃。
- 主表切换和审计日志写入在同一个 transaction 内完成。
- 符合当前 single-user / single-process MVP 的复杂度边界。

## 本次代码改动

- `memory/store.py`
  - 新增 `MemoryOpDraft` TypedDict。
- `sleep/tools.py`
  - `apply_consolidation` / `apply_promotions` / `apply_demotions` /
    `apply_resolutions` 不再直接写 `memory_ops_log`。
  - 这些函数只修改 staging 表,然后返回 `MemoryOpDraft` 列表。
  - `log_reflection` 改为 `draft_reflection_log`。
- `sleep/agent.py`
  - `SleepState` 增加 `pending_ops`。
  - 每个 phase 把返回的日志草稿 append 到 state。
  - `node_swap` 把 `pending_ops` 传给 `atomic_swap`。
- `sleep/staging.py`
  - `atomic_swap(..., pending_ops=...)` 在同一个 transaction 内:
    - merge 新 archival
    - rename staging/main
    - truncate staging
    - flush pending ops 到 `memory_ops_log`
    - commit

## 语义结果

- swap 成功:
  - 主表更新。
  - 本轮 Sleep 日志写入主 `memory_ops_log`。
- swap 失败:
  - 主表不变。
  - 本轮 Sleep 日志不写入主 `memory_ops_log`。
  - pending ops 随进程内 state 丢弃。

## 测试

新增/更新测试:

- `tests/test_sleep_staging.py::test_sleep_logs_are_pending_until_swap_commits`

该测试验证:

1. `apply_resolutions` 后主 `memory_ops_log` 仍为空。
2. `atomic_swap(..., pending_ops=...)` 成功后才出现 `sleep_resolve` 日志。

## 文档

- `docs/ARCHITECTURE.md` 更新 Sleep phase 说明:
  - phase 不再直接写主 `memory_ops_log`
  - phase 生成 `pending_ops`
  - `atomic_swap` 同事务 flush pending ops
