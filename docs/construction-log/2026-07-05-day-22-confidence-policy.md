# 2026-07-05 Day 22 - Confidence Policy Tightening

## 背景

用户发现 Mneme 里很多新记忆都是 `confidence=3`,包括一些包含"最近"、"当前"、"设备不在身边"等阶段性信息的事实。

问题不在数据库字段,而在 prompt 对 `confidence` 的解释太粗:

```text
明确长期事实用 3,不太确定用 2
```

这会让 Claude Code 把"用户明确说过"误等同于"长期稳定可 promote",导致阶段性事实也被打成 3。

## 新规则

`confidence` 表示这条记忆作为长期用户画像信号的稳定性 / 可复用性,不是 LLM 自报概率。

| 值 | 语义 | 例子 |
|---|---|---|
| 3 | stable long-term fact | 用户喜欢足球;用户偏好直接具体的中文解释 |
| 2 | stage-specific / recent but useful | 用户最近主要玩 CS2;用户当前 PS5/NS 不在身边 |
| 1 | tentative / inferred | 用户可能对某类游戏感兴趣 |

关键要求:

- 混合事实必须拆开。
- 不要把"长期偏好 + 最近状态"打包成一条 `confidence=3`。
- 临时细节可以跳过,或在确实有用时用 `confidence=2`。

## 本轮改动

- `/Users/mac/.claude/CLAUDE.md`
  - 更新 host-side confidence 规则。
  - 明确 3/2/1 语义。
  - 加入"混合事实拆开保存"。
- `src/mneme/mcp_server.py`
  - 更新 `remember` MCP tool docstring。
- `src/mneme/awake/agent.py`
  - 更新 Awake remember policy。
- `src/mneme/awake/tools.py`
  - 更新内部 `insert_archival_fact` policy。
- `tests/test_memory_prompt_policy.py`
  - 增加 prompt policy 断言:必须包含 `stable long-term`、`stage-specific`、`split`。
- `docs/ARCHITECTURE.md`
  - 补充 confidence 三档语义表。
- `docs/STUDY-NOTES.md`
  - 修正原来 low/medium/high 的粗略解释。

## 验证

```bash
/Users/mac/.local/bin/uv run pytest tests/test_memory_prompt_policy.py
# 2 passed

/Users/mac/.local/bin/uv run ruff check
# All checks passed!

/Users/mac/.local/bin/uv run mypy src
# Success: no issues found in 24 source files

curl -sS http://127.0.0.1:8000/health
# {"status":"ok","service":"mneme"}

zsh -ic 'cd /Users/mac; claude mcp list'
# mneme: http://127.0.0.1:8000/mcp (HTTP) - Connected

/Users/mac/.local/bin/uv run python -c 'from mneme import mcp_server; doc=mcp_server.remember.__doc__ or ""; print("stable long-term" in doc, "stage-specific" in doc, "split" in doc)'
# True True True
```

## 后续建议

历史上已经写入的混合事实可以后续做一次清理:

- 保留长期偏好事实为 `confidence=3`。
- 将阶段性事实拆成单独 fact 并改为 `confidence=2`。
- 删除明显临时或重复的 fact。
