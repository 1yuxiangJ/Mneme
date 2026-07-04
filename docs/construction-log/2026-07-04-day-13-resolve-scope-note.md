# 2026-07-04 Day 13 - 补充 resolve 作用范围说明

## 背景

用户追问:为什么 `resolve` 只解决 core 里的冲突,不解决 archival 里的冲突。

讨论结论:

- archival 是原始事实仓库,允许保留事实演化痕迹。
- archival 冲突可能在 `consolidate` / `demote` / `promote` 中被间接处理。
- core 是 Claude Code 会直接读取的用户画像,必须保持自洽。
- 如果没有 `resolve`,core 内部或 core 之间的存量矛盾只有在后续 `promote`
  刚好覆盖同一 block 时才可能被顺带修掉。

## 本次改动

- 在 `docs/ARCHITECTURE.md` 的 Node 6 `resolve` 后新增"为什么 resolve
  只处理 core 冲突,不直接处理 archival 冲突"。
- 增加冲突位置表:
  - archival vs archival
  - archival vs core
  - core vs core
  - core block 内部自相矛盾
- 明确四个 phase 的边界:
  - `consolidate`:压缩 archival 重复事实
  - `demote`:软删 archival 低价值旧事实
  - `promote`:把稳定 archival 综合进 core
  - `resolve`:检查 core 自洽性

## 状态

- 仅文档改动,没有修改代码。
- 后续可选扩展:`reconcile_archival` phase,用于处理 archival 冲突的 supersede
  标记、confidence 降级、时间范围补充。
