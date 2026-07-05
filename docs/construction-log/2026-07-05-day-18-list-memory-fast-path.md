# 2026-07-05 Day 18 - list_memory Direct DB Fast Path

## 背景

Claude Code 能连接 Mneme MCP,但调用 `list_memory` 时出现过 `Connection error`。排查后确认:

- `claude mcp list` 能连接 MCP server。
- debug log 显示失败发生在 `Calling MCP tool: list_memory` 之后。
- 旧实现里 `list_memory` 会绕到 Awake ReAct,也就是会依赖 DeepSeek/LLM provider。

结论:`list_memory` 本质是确定性只读概览,不应该为了统一架构强行走 Awake。

## 本轮改动

- `src/mneme/memory/store.py`
  - 新增 `ArchivalFactSnapshot`。
  - 新增 `list_archival_facts(session, limit=20)`。
- `src/mneme/mcp_server.py`
  - `list_memory()` 改成 direct DB fast path。
  - 返回 `status=ok`、`mode=direct_db`、core blocks、archival total、最多 20 条 active archival fact 摘要。
  - 保留 `mark_awake_activity()`,读概览仍会刷新 Sleep idle 计时。
- `tests/test_mcp_async_writes.py`
  - 新增测试:断言 `list_memory` 不调用 `_run_awake`,而是直接读 DB helper。
- 文档
  - `docs/ARCHITECTURE.md`:更新 `list_memory` 流程和两层 tool 映射。
  - `docs/STUDY-NOTES.md`:更新“写异步、读同步”和 Awake guardrail 说明。
  - `docs/CODE_REVIEW.md`:P2-15 标记为已落地。

## 设计取舍

- `recall` 继续走 Awake,因为它需要语义搜索和上下文组织。
- `list_memory` 不走 Awake,因为它是新 session 的启动用户画像入口,更看重稳定性、低延迟和低成本。
- 这个改法保留了 Mneme 的 Agent 性:需要推理和策略选择的路径仍由 Awake 处理;确定性只读路径直接查 DB。

## 验证

```bash
/Users/mac/.local/bin/uv run pytest tests/test_mcp_async_writes.py
# 3 passed

/Users/mac/.local/bin/uv run ruff check
# All checks passed!

/Users/mac/.local/bin/uv run mypy src
# Success: no issues found in 24 source files

curl -sS http://127.0.0.1:8000/health
# {"status":"ok","service":"mneme"}

zsh -ic 'cd /Users/mac/dream; claude mcp list'
# mneme: http://127.0.0.1:8000/mcp (HTTP) - Connected

zsh -ic 'cd /Users/mac/dream; claude -p --allowedTools mcp__mneme__list_memory -- "请调用 mneme 的 list_memory 工具，返回当前记忆概览。只做这个动作。"'
# 成功返回 5 个 core blocks + 3 条 archival facts;服务日志只有 CallToolRequest,没有 DeepSeek HTTP 请求。
```
