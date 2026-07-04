# 2026-07-04 Day 12 - ARCHITECTURE 补全 demote / resolve

## 背景

用户指出 `docs/ARCHITECTURE.md` 的 Sleep 模块流程里,`demote` 和 `resolve`
只写了"不在 plan 里 → 跳过",没有像 `snapshot` / `plan` / `consolidate`
/ `promote` / `reflect` / `swap` 一样展开说明。

这会导致学习和面试讲解时对两个 phase 没印象,也不利于后续解释
`sleep_demote`、`sleep_resolve` 这类审计日志设计。

## 本次改动

- 补全 `ARCHITECTURE.md` 中 Node 5 `demote` 的说明:
  - 为什么需要 demote
  - demote 只处理低价值 archival,不删除 core
  - stale candidates → LLM 判断 `FORGET` / `KEEP` → staging 软删
  - `sleep_demote` 日志
  - 保守规则和示例
- 补全 Node 6 `resolve` 的说明:
  - resolve 处理 core block 内部或 block 之间的语义冲突
  - 和 consolidate / demote / promote 的职责边界
  - 读取 core blocks + recent ops → LLM 输出修复方案
  - 更新 `core_blocks_staging`
  - 记录当前 MVP 仍复用 `sleep_consolidate`,后续应拆 `sleep_resolve`

## 状态

- 仅文档改动,没有修改代码。
- 后续如果执行 backlog 中的 "resolve 独立 op_type",需要再改:
  - `src/mneme/memory/store.py`
  - `src/mneme/db/schema.sql`
  - `src/mneme/sleep/tools.py`
  - 对应测试和文档
