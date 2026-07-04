# 2026-07-05 Day 16 - 文档状态 review

## 背景

用户要求对项目文档做一次 review:

- `ARCHITECTURE.md` 和 `STUDY-NOTES.md` 是用户主要阅读材料。
- 其他文档主要给 AI 使用,需要避免过时信息误导后续执行。

## 本次发现的问题

### 1. Study 笔记里有 Day 14 / Day 15 前的旧状态

过时点:

- `remember` 仍写成同步返回 `fact_id`。
- embedding 复用仍写成 "MVP 没做"。
- 写异步、读同步仍写成 "优化方向"。
- `resolve` 仍写成复用 `sleep_consolidate`。
- Sleep phase 仍写成直接 `INSERT INTO memory_ops_log`。
- Awake ReAct 卡死专题仍写成默认 `recursion_limit=25`、无 LLM timeout。
- `lock_timeout` 仍写成生产化待做。

### 2. Demo / Final verification 有旧输出

- `DEMO.md` 仍期待 `remember` 同步返回 `{status:"ok", fact_id:...}`。
- Sleep recent ops 示例未包含 `sleep_resolve`。

### 3. 当前状态文档质量门数量过旧

- `CODE_REVIEW.md` 和 `LOCAL_SETUP_STATUS.md` 仍写 `22 source files / 18 passed`。
- 当前质量门是 `24 source files / 28 passed`。

### 4. PLAN 是历史设计稿但没有显式说明

`PLAN.md` 里有 Day 01 的旧 API 设想,例如同步返回 fact_id。为避免后续 AI 当成当前实现,需要顶部标注它是历史设计稿。

## 本次修改

- `docs/ARCHITECTURE.md`
  - 事务说明补充 Awake / Sleep 的不同日志提交语义。
- `docs/STUDY-NOTES.md`
  - 更新 `memory_ops_log` op_type 表。
  - 更新 Awake remember 流程为 MCP accepted + 后台 ReAct。
  - 更新 embedding cache / 写异步读同步为已完成状态。
  - 更新 Sleep cycle trace 为 pending ops + swap 同事务 flush。
  - 更新 lock_timeout 和 Awake ReAct 卡死防护为当前实现。
- `docs/DEMO.md`
  - `remember` demo 改为 accepted + 等后台落库后 inspect。
  - Sleep recent ops 示例补 `sleep_resolve`。
- `docs/FINAL_VERIFICATION.md`
  - 补 `sleep_resolve` 和 pending ops 语义。
- `docs/PLAN.md`
  - 顶部加历史设计稿声明。
- `docs/CODE_REVIEW.md`
  - 更新当前质量门数量。
- `docs/LOCAL_SETUP_STATUS.md`
  - 更新日期和当前质量门数量。

## 未改范围

- `docs/construction-log/*` 中早期记录保留历史原貌,除非它们被当作当前状态文档使用。
- `docs/research-notes/*` 是外部资料摘录和早期 research notes,不强行改成当前实现。
