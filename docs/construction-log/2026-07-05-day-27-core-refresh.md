# 2026-07-05 Day 27 - Core Refresh Phase

> 历史记录:Day 27 是 Core Refresh 首次实现时的设计。Day 32 已把“Plan 可选 + active top-K + 最新 ops”升级为“每轮检查 + checkpoint 增量 ops + 自适应分块证据”,当前状态见 `2026-07-11-day-32-core-refresh-evidence.md`。

## 背景

用户指出一个架构缺口:

> demote 只对 archival 生效。如果 core 里有过时信息,怎么清除?

这是一个真实问题。此前 core 只有两条间接修正路径:

- `promote`:新高价值 archival 覆盖旧 core 表达
- `resolve`:修 core 内部矛盾

但这两条都不是专门处理 core 过期的机制。Core 是 Claude Code 会频繁读取的高密度用户画像,如果里面写入阶段性事实、过细生活细节或缺少当前支撑的旧表达,只靠 archival demote 不会自动清掉。

## 决策

新增独立 Sleep phase:

```text
core_refresh
```

放在 `resolve` 之后、`reflect` 之前:

```text
snapshot -> plan -> consolidate -> promote -> demote -> resolve
-> core_refresh -> reflect -> swap
```

不把这个能力塞进 `demote`,因为:

- `demote` 的职责是 archival 降噪,按 fact_id 软删原始事实。
- `core_refresh` 的职责是重写 core 用户画像,按 block 输出完整新 value。

不把它塞进 `resolve`,因为:

- `resolve` 处理逻辑矛盾。
- `core_refresh` 处理过期、过细、缺少支撑等 core 质量问题。

## 行为边界

`core_refresh` 会清:

- 过期阶段性内容
- 过细、不该常驻 core 的生活细节
- 被新事实覆盖的旧表达
- 缺少 active archival 支撑的低价值内容

`core_refresh` 不会清:

- 长期高显著偏好
- 沟通偏好、职业优先级、稳定习惯
- 只是暂时没被 recall 命中的核心画像

## 输入上下文设计

用户追问:

> core_refresh 只把新增 fact 加载进去不行吗?为什么还要看 ops_log?

结论:不行。`core_refresh` 不是只处理"新事实覆盖旧事实",它还要处理
"core 里有过细内容,但近期没有新事实触发它"这类质量问题。

三类输入分工:

| 输入 | 作用 |
|---|---|
| 当前 core_blocks_staging | 被审查、可能被重写的对象 |
| active archival top-K | 当前仍有效的事实支撑,按 salience / confidence / use_count 排序 |
| recent memory_ops_log | 说明 core 内容是怎么来的、最近做过哪些维护动作 |

只看新增 fact 的缺口:

- 能发现"用户最近开始重新用 IDEA"这类新事实覆盖旧事实。
- 不能发现"core 里有麦当劳薯条这种过细内容,但这一轮没有新增薯条 fact"。

`memory_ops_log` 的作用不是提供事实来源,而是提供变更历史。它能告诉 LLM:

- 某段 core 内容是否由之前的 `sleep_promote` 写入。
- 写入时的 reason 是否已经说明它只是低频/可引用信息。
- 最近是否刚通过 `sleep_core_refresh` 或 `sleep_resolve` 清理过类似内容。

这样可以避免低显著细节被反复写回 core。

## 代码改动

- `src/mneme/sleep/prompts.py`
  - 新增 `CORE_REFRESH_PROMPT`
  - `PLAN_PROMPT` 增加 `core_refresh` phase
- `src/mneme/sleep/tools.py`
  - 新增 `get_core_refresh_context`
  - 新增 `apply_core_refreshes`
- `src/mneme/sleep/agent.py`
  - 新增 `node_core_refresh`
  - StateGraph 从 8 节点变成 9 节点
  - summary 增加 `core_refresh_count`
- `src/mneme/memory/store.py`
  - `OpType` 增加 `sleep_core_refresh`
- `src/mneme/db/schema.sql`
  - ops_log 注释增加 `sleep_core_refresh`
- `tests/test_sleep_staging.py`
  - 新增 `test_core_refresh_logs_are_pending_until_swap_commits`

## 文档改动

- `docs/ARCHITECTURE.md`
  - Sleep 流程改为 9 节点
  - 新增 Node 7 `core_refresh`
  - 明确 core 过期不由 demote 处理
- `docs/STUDY-NOTES.md`
  - 学习笔记、sequence trace、面试话术同步改为 9 phase

## 验证记录

先补红灯测试:

```bash
/Users/mac/.local/bin/uv run pytest --run-integration \
  tests/test_sleep_staging.py::test_core_refresh_logs_are_pending_until_swap_commits
```

旧实现失败:

```text
ImportError: cannot import name 'apply_core_refreshes'
```

实现后通过:

```text
1 passed
```
