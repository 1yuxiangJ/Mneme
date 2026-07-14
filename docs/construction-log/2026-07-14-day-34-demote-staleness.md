# 2026-07-14 Day 34 - Demote Staleness Semantics

## 背景

Demote 原先用下面的条件判断事实是否过期:

```sql
last_used_at IS NULL OR last_used_at < cutoff
```

这把 `NULL` 错误解释成了“已经很久没用”。实际上它只表示 Fact 从未被 Recall,所以刚 Remember 的低信号 Fact 也可能在下一轮 Sleep 立即进入 Demote 候选。

## 实现

统一改为两段式时间语义:

```sql
(last_used_at IS NOT NULL AND last_used_at < cutoff)
OR (last_used_at IS NULL AND created_at < cutoff)
```

- 曾经使用过:按 `last_used_at` 判断是否超过 90 天。
- 从未使用过:按 `created_at` 判断是否超过 90 天。

`summarize_state()` 的 stale 计数和 `get_stale_candidates()` 的真实候选查询复用 `_STALE_FACT_AGE_PREDICATE`,保证 Plan 看到的数量与 Demote 实际处理口径一致。`DEMOTE_PROMPT` 也同步说明了两种时间来源。

## 测试

新增 PostgreSQL 集成测试覆盖:

1. 新建且从未使用的低信号 Fact 不进入候选。
2. 创建超过 90 天且从未使用的低信号 Fact 进入候选。
3. 创建时间很旧但最近使用过的低信号 Fact 不进入候选。
4. 最后使用超过 90 天的低信号 Fact 进入候选。
5. 即使时间很旧,高信号 Fact 也不进入 SQL 候选。

同时断言 Plan 的 `stale_archival_count` 与 Demote 返回的候选数量一致。

## 文件变更

- `src/mneme/sleep/tools.py`
- `src/mneme/sleep/prompts.py`
- `tests/test_sleep_staging.py`
- `docs/ARCHITECTURE.md`
- `docs/STUDY-NOTES.md`

## 结果

```text
ruff: All checks passed
mypy: Success: no issues found in 29 source files
pytest --run-integration: 58 passed, 1 warning
```

唯一 warning 是项目已有的 Starlette TestClient / httpx 弃用提示,与本次改动无关。
