# 2026-07-05 Day 26 - Promote Core Threshold Tightening

## 背景

手动运行一次 Sleep 后,链路成功:

```json
{
  "status": "ok",
  "plan": ["promote", "reflect"],
  "promote_count": 9
}
```

但结果暴露出 promote 门槛偏宽:一些 `salience=2` 的生活偏好,
例如具体食物偏好、细颗粒游戏偏好,也被升进了 `core_blocks.preferences`。

这类事实应该保留在 `archival_facts` 里,未来相关场景可通过 recall 找到;
但不应该占用 core_blocks 的长期画像空间。core 的目标是高密度、
高复用的用户画像,不是杂项喜好列表。

## 决策

promote 候选从:

```sql
use_count >= 5
AND confidence >= 3
AND stability = 'long_term'
AND salience >= 2
```

收紧为:

```sql
use_count >= 5
AND confidence >= 3
AND stability = 'long_term'
AND salience >= 3
```

语义:

- `salience=3`: 可以进入 core 候选。
- `salience=2`: 留在 archival,必要时进入 reflect/recall,不直接 promote。
- `salience=1`: 低频背景,通常只保留或后续 demote。

## preferences / habits 分流

本轮同时补充 prompt 规则:

- `preferences`:喜欢/不喜欢、价值判断、优先级、选择倾向。
- `habits`:长期重复行为、生活/工作节奏、常见放松方式。
- 细颗粒生活事实默认留 archival。只有当它表达出更高层长期模式时,
  才概括进入 core。

例子:

| fact | 处理 |
|---|---|
| 用户喜欢麦当劳现炸薯条 | archival,不进 core |
| 用户长期通过游戏、B站、抖音放松 | 可概括进 habits |
| 用户偏好直接具体的中文解释 | preferences |
| 用户 deadline 驱动、容易拖延 | habits |

## 代码改动

- `src/mneme/sleep/tools.py`
  - `get_promote_candidates(..., min_salience=3)`
  - `summarize_state.has_high_freq_archival` 同步使用 `salience >= 3`
- `src/mneme/sleep/prompts.py`
  - PROMOTE_PROMPT 写明 `salience=3`
  - 增加 preferences/habits 分流规则
  - 明确低/中显著生活细节不要进入 core
- `tests/test_sleep_staging.py`
  - 增加 `long_term + salience=2 + 高频` 的反例,确认不会进入 promote 候选
- `tests/test_demo_seed.py`
  - demo promotion-ready 条件同步改为 `salience>=3`

## 当前数据修正

因为 Day 25 手动 Sleep 已按旧规则把部分 `salience=2` 的细节写进
`core_blocks.preferences`,本轮做了一次数据修正:

- 从 `preferences` 移除:
  - 每周玩 CS2、箱子模式、不打高压竞技
  - PS5 / Nintendo Switch 当前不在身边
  - 喜欢麦当劳现炸薯条
- 保留在 `habits`:
  - 过去喜欢踢足球和健身
  - 最近休闲方式转为游戏、抖音、B站
- 不删除对应 archival facts,后续相关场景仍可通过 recall 查到。

修正方式:

- `core_blocks.preferences.version` 从 8 增加到 9
- `last_writer='sleep_agent'`
- 新增一条 `memory_ops_log(op_type='sleep_resolve')` 审计记录

## 文档改动

- `docs/ARCHITECTURE.md`
  - promote 条件更新为 `salience >= 3`
  - 补充 preferences/habits 分流规则
- `docs/STUDY-NOTES.md`
  - §5 Sleep 阶段表、§4.2 信号阈值、§8 面试话术同步更新

## 验证记录

先验证新规则红灯:

```bash
/Users/mac/.local/bin/uv run pytest --run-integration \
  tests/test_sleep_staging.py::test_promote_candidates_require_long_term_salient_explicit_memory \
  tests/test_demo_seed.py
```

旧实现失败,因为 `salience=2` 的长期生活细节仍被选进 promote 候选。

实现后同一命令通过:

```text
2 passed
```
