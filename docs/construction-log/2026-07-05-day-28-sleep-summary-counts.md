# 2026-07-05 Day 28 - Sleep Summary Count Semantics

## 背景

手动跑 Sleep 后返回:

```json
{
  "plan": ["promote", "reflect"],
  "promote_count": 5
}
```

但数据库里本轮只新增了 `sleep_reflect`,没有新增 `sleep_promote`。排查后确认:

- 旧 `promote_count` 统计的是 `len(promote_actions)`。
- `promote_actions` 是模型对 promote 候选的判断结果,里面可能包含 `SKIP`。
- 只有 `decision = "PROMOTE"` 的 action 才会真的改写 `core_blocks_staging` 并生成 `sleep_promote` pending op。

因此旧字段会让人误以为本轮实际 promote 了 5 条。

## 决策

保留 `promote_count`,但修正语义:

| 字段 | 含义 |
|---|---|
| `promote_candidate_count` | promote 阶段模型返回的判断数量,包含 `SKIP` |
| `promote_count` | 实际 `decision = "PROMOTE"` 的数量 |

这样旧字段名仍可用于判断 Sleep 是否真的修改 core,新增字段用于观察模型评估规模。

## 代码改动

- `src/mneme/sleep/agent.py`
  - 新增 `_count_decision()`。
  - `run_sleep_cycle()` summary 新增 `promote_candidate_count`。
  - `promote_count` 改为只统计 `decision = "PROMOTE"`。
- `tests/test_sleep_summary.py`
  - 新增单测,验证 3 个 promote 判断里只有 1 个 PROMOTE 时:
    - `promote_candidate_count = 3`
    - `promote_count = 1`

## 文档改动

- `docs/ARCHITECTURE.md`
  - Sleep summary 示例新增 `promote_candidate_count`。
  - 增加 `promote_candidate_count vs promote_count` 术语说明。
- `docs/STUDY-NOTES.md`
  - Sleep sequence trace 的 promote 节点补充 summary 统计语义。
- `docs/DEMO.md`
  - Sleep 输出示例同步新增 `promote_candidate_count`。

## 验证记录

先补红灯测试:

```bash
/Users/mac/.local/bin/uv run pytest tests/test_sleep_summary.py
```

旧实现失败:

```text
KeyError: 'promote_candidate_count'
```

实现后通过:

```text
tests/test_sleep_summary.py::test_sleep_summary_separates_promote_candidates_from_applied PASSED
```
