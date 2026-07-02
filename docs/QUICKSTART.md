# Quick Start

> 从空 mac 到 mneme 跑通 — 5 步。完整说明见 `docs/PLAN.md`。

## 前提

- macOS 14+
- Homebrew(`brew --version` 应该有输出)
- ~1 GB 磁盘空间(给 PostgreSQL + pgvector)
- **DeepSeek API key**([platform.deepseek.com](https://platform.deepseek.com),你已有额度)
- **DashScope API key**(仅 embedding,通义 `text-embedding-v3`,[dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/))

## 1. 解压

```bash
cd ~ && tar -xzf mneme.tar.gz
cd mneme
```

## 2. 跑 setup.sh

```bash
bash scripts/setup.sh
```

自动:
- `brew install postgresql@17 pgvector`
- `brew services start postgresql@17`
- 装 `uv`
- `createdb mneme` + `CREATE EXTENSION vector`
- 应用 `src/mneme/db/schema.sql`
- `uv sync`(装 Python 依赖)
- 拷贝 `.env.example` → `.env`(若不存在)

幂等,失败可重跑。

## 3. 填 `.env`

```bash
$EDITOR .env
```

最少填:
```
DEEPSEEK_API_KEY=sk-...
EMBED_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://mac@localhost:5432/mneme
```

> macOS Homebrew PG 默认无密码,DATABASE_URL 不填密码部分。用户名通常是你的 macOS 短用户名,本机是 `mac`。

## 4. 跑 service

终端 A 启动 Mneme 服务:

```bash
cd /Users/mac/dream
/Users/mac/.local/bin/uv run python -m mneme
```

期望日志:
```
... mneme startup; mcp at /mcp
... sleep scheduler disabled; set SLEEP_SCHEDULER_ENABLED=true to enable
INFO:     Uvicorn running on http://127.0.0.1:8000
```

终端 B 验证:
```bash
curl http://127.0.0.1:8000/health
# → {"status": "ok", "service": "mneme"}
```

## 5. 接入 Claude Code

项目根目录已经放了 project-scoped MCP 配置:

```text
.mcp.json
```

内容:

```json
{
  "mcpServers": {
    "mneme": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

也可以用 CLI 重新生成:

```bash
claude mcp add --transport http mneme --scope project http://127.0.0.1:8000/mcp
```

验证 MCP 连接:

```bash
scripts/claude-mneme.sh mcp list
# → mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected
```

启动 Claude Code:

```bash
cd /Users/mac/dream
scripts/claude-mneme.sh
```

为什么不用直接 `claude`:

```text
当前 shell 可能带有 HTTP_PROXY/HTTPS_PROXY 指向本地代理端口。
如果代理没启动,Claude Code 会连不上 Anthropic API 或本机 Mneme MCP。
scripts/claude-mneme.sh 会清理这些代理变量,并设置 NO_PROXY。
```

首次进入项目目录时批准 `.mcp.json` 里的 `mneme` server。批准后可以在 Claude Code 里说:

```text
调用 mneme 的 list_memory，看看当前记忆。
```

已验证的工具:

```text
mcp__mneme__list_memory
mcp__mneme__remember
mcp__mneme__recall
mcp__mneme__forget
```

---

## 验证(可选)

### 强制触发 Sleep cycle(不等 30 min idle)

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
```

期望输出:

```json
{
  "status": "ok",
  "plan": ["reflect"]
}
```

如果当前 memory 很少,`plan` 只跑 `reflect` 是正常的。

### 查看当前 memory / ops_log 快照

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10
```

输出包含:

```text
core_blocks
archival_facts
recent_ops
```

### 跑 unit tests

```bash
uv run pytest                       # 只跑 unit(不需要 DB 也能跑 test_config)
uv run pytest --run-integration     # 加 integration(需要 mneme_test 库)
```

---

## 常见问题

| 症状 | 修法 |
|---|---|
| `pg_isready` 一直 fail | `brew services restart postgresql@17` |
| `uv: command not found` | `export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"` |
| `extension "vector" does not exist` | `psql mneme -c "CREATE EXTENSION vector;"` |
| `8000 port already in use` | 改 `.env` 的 `MCP_SERVER_PORT=8001` |
| `claude mcp list` 显示 Failed to connect | 用 `scripts/claude-mneme.sh mcp list`,不要直接用带坏代理的 `claude` |
| Claude Code 里看不到 Mneme 工具 | 确认 Mneme 服务在终端 A 跑着,再确认 `scripts/claude-mneme.sh mcp list` 是 `✔ Connected` |
| `pyproject.toml 找不到 src` | `cat pyproject.toml` 应该是 `packages = ["src/mneme"]` |
| `cannot import name 'X' from 'langgraph'` | 见 `docs/CODE_REVIEW.md` P1 risks |

---

## 卸载

```bash
brew services stop postgresql@17
dropdb mneme
rm -rf ~/mneme
```
