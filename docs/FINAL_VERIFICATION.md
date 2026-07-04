# Final Verification Checklist

这份清单只放最后人工确认项。开发过程中不需要每一步手动验证。

## 1. 启动服务

```bash
cd /Users/mac/dream
/Users/mac/.local/bin/uv run python -m mneme
```

另开终端:

```bash
curl -sS http://127.0.0.1:8000/health
```

期望:

```json
{"status":"ok","service":"mneme"}
```

## 2. Claude Code MCP

```bash
cd /Users/mac/dream
scripts/claude-mneme.sh mcp list
```

期望:

```text
mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected
```

## 3. Demo Data

真实 dogfood 数据优先。如果本地 facts 不够,再显式写入 demo-tagged facts:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --yes
```

说明:

```text
demo facts 会带 demo-seed tag。
高置信 demo facts 会被设置为 promotion-ready use_count。
如果之前已经 seed 过,再次执行会刷新已有 demo facts 的 usage 信号。
```

也可以用一条命令完成 seed + Sleep + inspect:

```bash
/Users/mac/.local/bin/uv run python scripts/run_demo_cycle.py --seed --yes
```

查看当前状态:

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10 --include-deleted
```

## 4. Sleep Demo

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py --min-archival-count 0
```

期望:

```text
status = ok
plan 至少包含 reflect;数据足够时应出现 promote / consolidate
```

再次查看:

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10
```

重点看:

```text
recent_ops 里有 sleep_reflect
如果触发 promote,core_blocks version 会增加,recent_ops 有 sleep_promote
如果触发 consolidate,recent_ops 有 sleep_consolidate
如果触发 resolve,recent_ops 有 sleep_resolve
```

Sleep 日志是 pending ops 语义:只有 `atomic_swap` 成功后才会写入主
`memory_ops_log`;如果 swap 因 lock timeout 失败,主表不变,本轮 Sleep 日志也不会写入。

清理 demo seed 数据:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --cleanup --yes
```

## 5. Quality Gate

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```

当前期望:

```text
ruff: All checks passed
mypy: Success, no issues found
pytest: all tests passed
```
