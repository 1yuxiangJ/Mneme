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

当前本机额外注册了 user-scoped MCP 配置,所以 Claude Code 客户端可以在任意目录直接使用 Mneme:

```bash
claude mcp add --transport http --scope user mneme http://127.0.0.1:8000/mcp
```

当前本机还在全局 Claude 指令里配置了主动记忆策略:

```text
/Users/mac/.claude/CLAUDE.md
```

这一步很关键: MCP tool description 只能告诉 Claude Code "remember 工具能做什么",但不会强制它主动用。全局指令负责告诉 Claude Code:遇到长期稳定的用户事实时,不要等用户说"记一下",应主动调用 Mneme。

当前全局指令还要求主动写入后给用户一个轻量确认,例如:

```text
我已记住:你长期通过足球、游戏、B 站和抖音放松。
```

这样用户不需要去数据库里猜 Claude 是否已经写入。

两份配置的职责不同:

| 配置 | 位置 | 作用 |
|---|---|---|
| project scope | `/Users/mac/dream/.mcp.json` | 项目自描述,别人 clone 后知道怎么接 Mneme |
| user scope | `/Users/mac/.claude.json` | 本机任意目录启动 `claude` 都能看到 Mneme |

验证 MCP 连接(不需要在 dream 目录):

```bash
claude mcp list
# → mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected
```

启动 Claude Code:

```bash
claude
```

注意:这只解决 **Claude Code 客户端任意目录可用**。Mneme service 本身仍然需要先启动:

```bash
cd /Users/mac/dream
/Users/mac/.local/bin/uv run python -m mneme
```

为什么现在可以直接 `claude`:

```text
本机 ~/.zshrc 已配置透明 claude() 函数:
- 子 shell 内清理 HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy
- 设置 NO_PROXY=127.0.0.1,localhost,::1
- 再调用真实 Claude CLI

所以你仍然输入 claude,但本地 Mneme MCP 不会被错误代理影响。
scripts/claude-mneme.sh 保留为 fallback。
```

批准 `mneme` server 后,可以在 Claude Code 里说:

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

想在本地演示 promote / consolidate,可以先显式写入一组 demo-tagged facts:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --yes
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py --min-archival-count 0
```

`seed_demo_memory.py` 默认不会写库,必须带 `--yes`。这些 fact 会带
`demo-seed` tag,方便后续识别。高置信 demo facts 会带 promotion-ready
`use_count`,用于触发 Sleep promote;如果 demo facts 已存在,seed 命令会刷新这些
usage 信号。

也可以用一条命令完成 seed + Sleep + inspect:

```bash
/Users/mac/.local/bin/uv run python scripts/run_demo_cycle.py --seed --yes
```

清理 demo seed 数据:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --cleanup --yes
```

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

如果要看 soft-deleted facts:

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10 --include-deleted
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
| `claude mcp list` 显示 Failed to connect | 先确认 Mneme 服务在跑:`curl http://127.0.0.1:8000/health`;再开新终端让 `.zshrc` 生效;仍失败再用 `scripts/claude-mneme.sh mcp list` fallback |
| Claude Code 里看不到 Mneme 工具 | 确认 Mneme 服务在终端 A 跑着,再确认 `claude mcp list` 是 `✔ Connected` |
| `pyproject.toml 找不到 src` | `cat pyproject.toml` 应该是 `packages = ["src/mneme"]` |
| `cannot import name 'X' from 'langgraph'` | 见 `docs/CODE_REVIEW.md` P1 risks |

---

## 卸载

```bash
brew services stop postgresql@17
dropdb mneme
rm -rf ~/mneme
```
