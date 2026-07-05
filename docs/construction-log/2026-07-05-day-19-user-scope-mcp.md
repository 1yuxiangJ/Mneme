# 2026-07-05 Day 19 - Claude Code User-Scope MCP

## 背景

用户希望不需要 `cd /Users/mac/dream` 就能在 Claude Code 中使用 Mneme。

Day 17 已解决"直接输入 `claude` 不走代理污染"的问题,但当时 MCP server 仍主要依赖 project-scoped `.mcp.json`,所以离开项目目录后 `claude mcp list` 看不到 Mneme。

## 本轮操作

新增 Claude Code user-scoped MCP 配置:

```bash
claude mcp add --transport http --scope user mneme http://127.0.0.1:8000/mcp
```

实际写入:

```text
/Users/mac/.claude.json
```

保留 project-scoped 配置:

```text
/Users/mac/dream/.mcp.json
```

## 当前语义

- Mneme service 仍然需要从项目目录启动:

```bash
cd /Users/mac/dream
/Users/mac/.local/bin/uv run python -m mneme
```

- Claude Code 客户端可以在任意目录启动:

```bash
claude
```

- project scope 用于仓库自描述和可移植性。
- user scope 用于本机全局可用。

## 验证

从 `/Users/mac` 目录验证,不进入 dream:

```bash
zsh -ic 'cd /Users/mac; claude mcp list'
# mneme: http://127.0.0.1:8000/mcp (HTTP) - Connected

zsh -ic 'cd /Users/mac; claude -p --allowedTools mcp__mneme__list_memory -- "请调用 mneme 的 list_memory 工具，返回当前记忆概览。只做这个动作。"'
# 成功返回 5 个 core blocks + 3 条 archival facts
```

## 文档同步

- `README.md`:说明 Claude Code 客户端任意目录可用。
- `docs/QUICKSTART.md`:补充 user scope / project scope 的区别。
- `docs/FINAL_VERIFICATION.md`:MCP 验证不再要求 `cd /Users/mac/dream`。
- `docs/LOCAL_SETUP_STATUS.md`:记录当前 user-scope 配置状态。
