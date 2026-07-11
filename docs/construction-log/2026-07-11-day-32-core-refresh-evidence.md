# 2026-07-11 Day 32 - Core Refresh Evidence Loading

## 背景

手动 Sleep 时,Plan 选了 `promote / demote / reflect`,没有选 `core_refresh`。排查发现两个问题:

1. Plan 要先判断 Core 是否过时,但 Plan 只拿到 Core 和几个聚合计数,没有 Refresh 真正依赖的 Archival 证据和变更历史。
2. 旧 `get_core_refresh_context()` 只加载全局排序前 30 条 active facts 和最新 20 条 ops。全局 Top 30 可能被单一主题占满,新而低使用次数的事实也容易被漏掉;固定 20 条 ops 可能被批量 remember 挤掉。

## 决策

### 1. Refresh 每轮检查

运行时会保证 `core_refresh` 出现在 plan,节点不再依赖 LLM 是否选中才进入。

每轮检查不等于每轮调 LLM:

```text
无非空 Core
  -> 直接跳过

已有 checkpoint,且之后无相关变化
  -> 直接跳过 LLM

首次检查 / 存在已提交变化 / 本轮有 pending 变化
  -> 加载证据并调 LLM 决定 REFRESH / KEEP
```

### 2. 用 ops_log 作增量游标

每次成功检查生成:

```text
op_type   = sleep_core_refresh
target_id = __checkpoint__
```

checkpoint 是 pending op,只有最终 atomic swap 成功才写入主 `memory_ops_log`。如果 LLM、staging 修改或 swap 失败,游标不会推进。

下一轮读取 checkpoint op id 之后的:

```text
remember / forget / sleep_consolidate / sleep_promote / sleep_demote /
sleep_resolve / sleep_core_refresh
```

并合并本轮尚未 flush 的 pending ops。

### 3. 自适应事实证据

```text
active archival <= 200
  -> 加载全部 active facts

active archival > 200
  -> 每个非空 Core block 语义 Top 8
  -> + checkpoint 后变更的全部 archival facts
  -> + confidence=3, long_term, salience=3 的全局 Top 10
  -> 按 fact id 去重,并保留 evidence_reasons / semantic_distances
```

如果 Awake 在 Sleep snapshot 后才 remember / forget,变更行可能尚未进 staging。Refresh 会同时读 staging 和当前主表,并按 swap 相同规则合并 `use_count / last_used_at / is_deleted`,避免 checkpoint 跨过未真正看到的变化。

## 可配置参数

```env
CORE_REFRESH_ALL_FACTS_THRESHOLD=200
CORE_REFRESH_PER_BLOCK_LIMIT=8
CORE_REFRESH_HIGH_SIGNAL_LIMIT=10
```

## 可观测返回

Sleep summary 新增 / 修正:

```text
core_refresh_checked
core_refresh_evidence_mode     # none / all_active / adaptive
core_refresh_skip_reason
core_refresh_candidate_count   # LLM 返回的 REFRESH + KEEP 数
core_refresh_count             # 真正 REFRESH 的 block 数
```

## 代码与测试

- `src/mneme/sleep/agent.py`:每轮 Refresh 检查、无变化 fast path、summary 语义。
- `src/mneme/sleep/tools.py`:checkpoint 增量 ops、全量 / 自适应证据、snapshot 后 Awake 变更合并。
- `src/mneme/sleep/prompts.py`:Plan 强制检查和 Refresh evidence metadata。
- `src/mneme/config.py` / `.env` / `.env.example`:新增三个参数。
- `tests/test_sleep_core_refresh.py`:验证 Plan 补全、Plan 漏选时仍执行、无变化不调 LLM。
- `tests/test_sleep_staging.py`:真实 PostgreSQL 验证全量、自适应、checkpoint、snapshot 后新 fact 和 checkpoint 原子提交。

## 验证记录

定向检查:

```text
ruff: All checks passed
mypy: Success, no issues found in 36 source files
pytest: 20 passed
```

完整质量门:

```bash
/Users/mac/.local/bin/uv run ruff check src tests scripts
/Users/mac/.local/bin/uv run mypy src scripts
/Users/mac/.local/bin/uv run pytest --run-integration
```

结果:

```text
ruff: All checks passed
mypy: Success, no issues found in 36 source files
pytest: 57 passed, 1 warning
```

warning 为已知的 Starlette `TestClient` / `httpx` 弃用提示,与本次 Refresh 改动无关。
