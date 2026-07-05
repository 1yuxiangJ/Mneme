# 2026-07-05 Day 17 - 直接启动 Claude Code

## 背景

用户希望不再记 `scripts/claude-mneme.sh`,而是在项目目录里直接执行:

```bash
claude
```

也能连接 Mneme MCP。

此前必须用脚本的原因:

- 当前 shell 可能继承 `HTTP_PROXY` / `HTTPS_PROXY`。
- Claude Code 访问 `http://127.0.0.1:8000/mcp` 时可能错误走代理。
- `scripts/claude-mneme.sh` 会清理代理并设置 `NO_PROXY`。

## 本次改动

在 `/Users/mac/.zshrc` 中新增透明 `claude()` 函数:

```zsh
function claude() (
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
  export NO_PROXY="127.0.0.1,localhost,::1${NO_PROXY:+,$NO_PROXY}"
  export no_proxy="$NO_PROXY"
  command claude "$@"
)
```

特点:

- 用户仍然输入 `claude`。
- 函数运行在子 shell,不会污染当前终端的代理变量。
- `command claude` 会调用真实 Claude CLI,不会递归调用函数自身。
- `scripts/claude-mneme.sh` 保留为 fallback。

## 验证

使用新 zsh 会话验证:

```bash
zsh -ic 'cd /Users/mac/dream; claude mcp get mneme'
```

结果:

```text
mneme:
  Scope: Project config (shared via .mcp.json)
  Status: ✔ Connected
  Type: http
  URL: http://127.0.0.1:8000/mcp
```

## 文档同步

- `README.md`:Quick Start 改为直接 `claude`。
- `docs/QUICKSTART.md`:MCP 验证和启动命令改为直接 `claude`。
- `docs/FINAL_VERIFICATION.md`:验证命令改为 `claude mcp list`。
- `docs/LOCAL_SETUP_STATUS.md`:当前验证命令改为 `claude mcp list`。
