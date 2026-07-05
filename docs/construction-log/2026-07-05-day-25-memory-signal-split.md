# 2026-07-05 Day 25 - Memory Signal Split

## 背景

用户在 DataGrip 里观察到一个问题:绝大多数 archival fact 的
`confidence` 都是 3。原因是旧设计把三件事混在一个字段里:

- 事实是否确定
- 这件事是否长期稳定
- 这件事未来协作价值高不高

只要用户明确说过,模型就倾向于给 `confidence=3`,导致阶段性事实
(例如最近主要玩 CS2、本机项目路径、当前工具链)和长期画像事实
(例如沟通偏好、长期兴趣)失去区分度。

## 决策

把记忆信号拆成三列:

| 字段 | 含义 | 取值 |
|---|---|---|
| `confidence` | 事实确定性 | 1/2/3 |
| `stability` | 时间跨度 | `long_term` / `stage` / `temporary` |
| `salience` | 未来协作价值 | 1/2/3 |

旧数据不置空。新增字段有默认值:

- `stability = 'long_term'`
- `salience = 2`

后续通过 `scripts/relabel_memory_signals.py` 让模型对已有事实重新判断
`stability/salience`。脚本默认 dry-run,只有 `--apply` 才写库。

## 代码改动

- `src/mneme/db/schema.sql`
  - `archival_facts` 新增 `stability` / `salience`
  - 加入 idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- `src/mneme/db/models.py`
  - `ArchivalFact` ORM 增加两个字段
- `src/mneme/memory/store.py`
  - archival snapshot/search/list 结果透出 `stability/salience`
  - `insert_archival` 支持新参数,并保留默认值兼容旧调用
- `src/mneme/mcp_server.py`
  - `remember` MCP tool 签名增加 `stability/salience`
  - `list_memory` 返回 archival facts 时包含两列
- `src/mneme/awake/agent.py` / `src/mneme/awake/tools.py`
  - Awake prompt 和内部 insert tool 使用三信号策略
- `src/mneme/sleep/tools.py` / `src/mneme/sleep/prompts.py`
  - promote 候选改为:
    `use_count >= 5 AND confidence >= 3 AND stability='long_term' AND salience >= 2`
  - demote 候选改为:
    stale 且 `(confidence <= 1 OR stability='temporary' OR salience <= 1)`
  - consolidate/search/reflection 输出带上新信号
- `src/mneme/memory/inspect.py`
  - inspect 输出包含新信号
- `src/mneme/demo_seed.py`
  - demo facts 显式标注 `stability/salience`
- `scripts/relabel_memory_signals.py`
  - 新增旧记忆重标脚本,默认 dry-run

## 文档改动

- `docs/ARCHITECTURE.md`
  - `remember` 签名、参数解释、Sleep promote/demote 条件更新为三信号模型
- `docs/STUDY-NOTES.md`
  - §4.2 数据模型、§5 Sleep 流程、§8 面试话术同步更新
- `/Users/mac/.claude/CLAUDE.md`
  - host-side 主动记忆策略改为传入 `confidence/stability/salience`

## 旧数据迁移记录

数据库 schema 已迁移:

```sql
ALTER TABLE archival_facts ADD COLUMN IF NOT EXISTS stability TEXT NOT NULL DEFAULT 'long_term';
ALTER TABLE archival_facts ADD COLUMN IF NOT EXISTS salience SMALLINT NOT NULL DEFAULT 2;
```

旧数据先通过默认值保证字段非空,随后运行模型重标:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  /Users/mac/.local/bin/uv run python scripts/relabel_memory_signals.py \
  --limit 100 --apply
```

结果:

- loaded_count: 24
- accepted_count: 24
- 全部 active archival facts 已写入模型判断后的 `stability/salience`

当前分布:

```text
long_term / salience=2: 11
long_term / salience=3: 6
stage     / salience=3: 7
```

注意:本机 shell 里带代理环境变量时 DeepSeek 连接失败。重标脚本需要清理
`HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy` 后运行;Claude MCP 对 localhost
仍然需要 `NO_PROXY=127.0.0.1,localhost`。

## 验证记录

先补了失败用例:

- `tests/test_memory_prompt_policy.py`
- `tests/test_mcp_async_writes.py`
- `tests/test_demo_seed.py`
- `tests/test_relabel_memory_signals.py`
- `tests/test_sleep_staging.py`

阶段验证:

```bash
/Users/mac/.local/bin/uv run pytest \
  tests/test_memory_prompt_policy.py \
  tests/test_mcp_async_writes.py \
  tests/test_demo_seed.py \
  tests/test_relabel_memory_signals.py
```

结果:9 passed。

完整验证:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src scripts
/Users/mac/.local/bin/uv run pytest
/Users/mac/.local/bin/uv run pytest --run-integration \
  tests/test_memory_store.py tests/test_sleep_staging.py
```

结果:

- Ruff: All checks passed
- mypy: Success, no issues found
- 默认测试:22 passed,13 skipped,1 warning
- 集成测试:13 passed
