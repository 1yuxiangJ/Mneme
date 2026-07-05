# 2026-07-05 Day 20 - Lifestyle Memory Policy

## 背景

用户用 Claude Code 做用户画像访谈时,提到了:

- 喜欢足球。
- 以前经常健身,最近暂停。
- 最近主要玩 CS2。
- 以前玩 PS5 / NS 上的单机游戏更多。
- 闲暇时会刷抖音和 B 站。

Claude Code 继续追问,但没有主动调用 Mneme `remember`。判断原因:原 MCP `remember` tool description 太偏工作/学习/技术画像,只写了 preferences / habits / lessons / identity,没有明确长期生活偏好、兴趣、娱乐方式也应该记。

## 本轮改动

- `src/mneme/mcp_server.py`
  - 强化 `remember` MCP tool docstring。
  - 明确长期稳定用户事实包括:
    - lifestyle habits
    - hobbies
    - entertainment preferences
    - relaxation patterns
    - product tastes
    - stable likes/dislikes
  - 明确不要记:
    - temporary state
    - one-off events
    - today's plan
    - short-term mood
  - 对 recent/temporary 表述要求先追问确认是否长期稳定。
- `src/mneme/awake/agent.py`
  - 同步扩展 Awake domain constraint。
- `src/mneme/awake/tools.py`
  - 同步扩展内部 `insert_archival_fact` policy。
- `tests/test_memory_prompt_policy.py`
  - 新增 prompt policy 回归测试,防止以后工具描述退回技术偏向。
- 文档
  - `docs/ARCHITECTURE.md`:补充生活偏好属于 `remember` 范围。
  - `docs/STUDY-NOTES.md`:补充 Day 20 触发边界变化。
  - `docs/DEMO.md`:新增生活偏好自动 remember 测试变体。

## 当前策略

应该记:

- "用户喜欢足球。"
- "用户长期通过游戏、B 站、抖音放松。"
- "用户偏好 CS2 这类需要反应和团队配合的游戏。"

需要追问后再记:

- "最近暂停健身。"
- "最近游戏机不在身边,所以基本只玩 CS2。"

不应该记:

- "今天累。"
- "这周末打算玩游戏。"
- "刚才刷到一个视频。"

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

/Users/mac/.local/bin/uv run python -c 'from mneme import mcp_server; doc=mcp_server.remember.__doc__ or ""; print("hobbies" in doc, "lifestyle" in doc, "temporary" in doc)'
# True True True
```
