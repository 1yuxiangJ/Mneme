# 施工记录 — 2026-06-17 Day 03: Sleep Agent 框架

> 注:仍是 2026-06-17 同一天(三个 day-NN 文件全在一天写完的极端情况)。用户拍板 "环境延后,代码继续",所以连续把 Day 02b(Awake)和 Day 03(Sleep)都写完。

## 本次目标

不依赖环境的前提下,把 **Sleep agent 完整框架** 写好——包括 5 个 reflection prompts、staging snapshot + atomic swap、LangGraph StateGraph、APScheduler 触发、跟 Awake 的 activity 联动。

Prompt 内容调优留到家里跑 LLM 时做。

## 已完成

### 新增文件(5)

```
src/dream/sleep/prompts.py            # 6 个 prompt 模板(PLAN/CONSOLIDATE/PROMOTE/DEMOTE/RESOLVE/REFLECT)
src/dream/sleep/staging.py            # snapshot + atomic_swap + cleanup
src/dream/sleep/tools.py              # 数据访问 + 决策应用(读 main + 写 staging)
src/dream/sleep/agent.py              # LangGraph StateGraph + run_sleep_cycle() 入口
src/dream/sleep/scheduler.py          # APScheduler 触发器 + idle detection + activity 标记
tests/test_sleep_staging.py           # 4 个 @skip 测试骨架
docs/construction-log/2026-06-17-day-03-sleep-agent.md  # 本文件
```

### 修改(2)

- `src/dream/main.py`:`lifespan` 解开 scheduler 启动/关闭注释,Sleep agent 启动时即拉起
- `src/dream/mcp_server.py`:加 `mark_awake_activity()` 包装层,每次 MCP tool 调用都重置 idle 计时器

## Sleep 架构(终于落地)

```
                    APScheduler
                        │
        ┌───────────────┼─────────────┐
        ▼               ▼             ▼
   idle ≥ 30min    cron 03:00     (single-flight)
        └───────────────┬─────────────┘
                        ▼
                 run_sleep_cycle()
                        │
                        ▼
              LangGraph StateGraph
                        │
   START → snapshot → plan → consolidate → promote → demote → resolve → reflect → swap → END
                        │       │ skip if not in plan │       │      │
                        │       └─── conditional ────┘       │      │
                        │                                     │      │
                        ▼                                     ▼      ▼
              clone main→staging                       per-node:
                                                       1. read state
                                                       2. format prompt with state
                                                       3. LLM call (DeepSeek)
                                                       4. parse JSON action list
                                                       5. apply to staging
                                                       6. log to memory_ops_log
                        │
                        ▼
              atomic_swap: BEGIN TX → merge new archival
              (created_at > snapshot_ts) → 3-way RENAME → COMMIT
```

## 关键决策 / 发现

### 1. 5 个 phase 不是固定跑,**LLM 决定 plan**

PLAN phase 把当前 memory state 喂给 LLM,LLM 输出 `{"phases": ["consolidate","promote","reflect"], "reason": "..."}`。后续 node 看自己是否在 plan 里,不在就 no-op pass through。

→ **真正的 LLM-driven autonomous decision**,不是 cron + SQL update。这是项目"算 agent"的灵魂。

### 2. **Read-only primary 在 graph 层落地**

- Sleep 的 promote / resolve / 部分 consolidate 是**仅有的** core_blocks 写入路径
- `dream.memory.store.write_core_block` 应用层守卫:non-sleep actor 试图写 → `PermissionError` + 日志
- `core_blocks.last_writer` DB 字段:再加一道自检
- Sleep agent 内部的 `apply_promotions` / `apply_resolutions` 用 SQL 直接更新 `core_blocks_staging`,不走 `write_core_block`(staging 表里写无所谓,反正最终 atomic_swap 才生效)

### 3. Budget 强制只做 wall_time(MVP 简化)

每个 node 进入时 `_budget_ok(state)` 检查 monotonic deadline,超了就 pass through 后面的 phase 直接到 swap。

token budget 没强制——Day 05+ 改。

### 4. Staging swap 用**三步 rename + tmp 名**

```sql
ALTER TABLE main          RENAME TO main_tmp_swap;
ALTER TABLE staging       RENAME TO main;
ALTER TABLE main_tmp_swap RENAME TO staging;
TRUNCATE staging;
```

(在同一个 transaction 里,PostgreSQL 支持 ALTER TABLE RENAME 在 transaction 内)

期间 Awake 插入的新 archival(`created_at > snapshot_ts`)在 swap 前 MERGE INTO staging。

**MVP trade-off**:Awake `UPDATE`(mark_archival_used 改 use_count)可能被覆盖。MVP 接受;Day 05+ 加 row-level merge。

### 5. APScheduler 用 `AsyncIOScheduler` + `IntervalTrigger(60s)` + `CronTrigger`

- Idle:每 60s 跑 `_idle_tick`,如果 `_idle_seconds() >= threshold` 就触发
- Cron:每天 03:00 强制 `_cron_tick`(兜底)
- 都用 `max_instances=1` + `coalesce=True`(同种 trigger 多次堆积时只执行一次)
- 跨 trigger 用模块级 `_cycle_running` flag 防并发

### 6. Activity 标记跨模块协作

```
mcp_server.py:每个 MCP tool 调用 → mark_awake_activity()
                                        ↓
                                   scheduler.py:_last_awake_activity_monotonic = now()
                                        ↓
                                   _idle_tick(): if idle ≥ threshold: fire
```

`mcp_server.py` 用 `run_awake` 包装函数,把 `_run_awake` (来自 awake/agent.py) 和 `mark_awake_activity` 两件事串起来。

避免循环 import:`scheduler.start_sleep_scheduler()` 才 `from dream.sleep.agent import run_sleep_cycle`(lazy)。

## ⚠️ 没跑过的 5 + 4 个 known risk

旧的 5(来自 Day 02b):
1. LangGraph `create_react_agent` API 签名
2. SQLAlchemy `Mapped[Optional[X]]` 写法
3. pgvector `.cosine_distance` 方法
4. `FastMCP(host=, port=)` 构造参数
5. `mcp.streamable_http_app()` 跟 Mount 配合

新增 4 个 Day 03 risk:
6. **`langgraph.graph.StateGraph` API**:`add_node`/`add_edge` 用法看 LangGraph 版本可能微调
7. **`json.dumps(... default=str)`** 处理 datetime 应该 OK,但 LLM 解 JSON 时如果遇到 `"...T..."` 字符串可能要再 parse
8. **pgvector 距离运算符 `<=>`** 在 raw SQL 里写法:可能需要 cast 或 explicit operator class
9. **`apscheduler.schedulers.asyncio.AsyncIOScheduler`** 在 Starlette lifespan 里启动:某些版本需要 event loop 已存在;启动时机已经放对(`async with` 内)

→ 仍然全是 1-line 改动,跑起来看报错再改。

## 未完成 / 阻塞

### 阻塞(等环境)

- [ ] 跑 Sleep cycle,看 prompt 输出合不合理
- [ ] Reflection prompt 调优(必须看 5-10 次真实 LLM 输出迭代)
- [ ] Staging swap SQL 在真 PG 上 stress test(并发场景)
- [ ] 验证 APScheduler 在 uvicorn workers 下不重复跑(单 worker 没问题,多 worker 需要 distributed lock)

### 软待办

- [ ] Sleep cycle 的 e2e 集成测试(假数据 seed + run cycle + 验证 core block 改了)
- [ ] memory_ops_log 查看 CLI/REST endpoint(方便 demo 时 review)
- [ ] Sleep cycle 中途 abort 的恢复测试(deadline 触发 / 异常 / kill -9)

## 下次接着做(回家)

按 Day 02b 末尾的"回家路径"做 + 新增 Sleep 验证:

### Step 1-5(沿用 Day 02b 末尾)
微信传 → setup.sh → 填 .env → 跑 unit test → 启动 service → curl health

### Step 6(新增):验证 Sleep cycle

```bash
# 启动后 30 min 内不要调任何 MCP tool,模拟 idle
# 看 logs:
tail -f logs/dream.log
# 应该看到:
#   sleep scheduler started: idle_threshold=1800s, daily_cron=03:00
# 30 min 后:
#   sleep cycle starting (budget=300s)
#   snapshot_to_staging @ ...
#   plan: phases=['reflect'] reason=archival_count<10, skip everything
#   ...

# 强制触发(不等 30 min):
# 直接调:
uv run python -c "
import asyncio
from dream.sleep.agent import run_sleep_cycle
print(asyncio.run(run_sleep_cycle()))
"
```

### Step 7(新增):跑通 e2e 后,seed 真实 data

跟 Claude Code 聊 2-3 天,自然积累 archival。
然后再触发 sleep,看 promote / consolidate 是否做了合理决策。

### Step 8(新增):Reflection prompt 调优

Day 05 主要工作:
- 看 sleep 的实际输出(`memory_ops_log` 里 `sleep_reflect` 行)
- 如果太啰嗦 / 太省 / 抓错重点 → 改 `sleep/prompts.py` 的 REFLECT_PROMPT
- 同理 consolidate / promote / demote prompt

## 接续指引(给新窗口的 Claude 看)

新窗口接 "继续 dream 项目":

1. 读 `~/dream/README.md`
2. 读 `~/dream/docs/PLAN.md`(尤其 §17 changelog,确认 read-only primary 版)
3. 读 `~/dream/docs/DECISIONS.md`(Q1-Q14)
4. 读最新 construction-log(本文件就是最新)
5. 读 `~/dream/docs/research-notes/*` 4 份
6. **特别注意**:Day 02b + Day 03 全部代码**未跑通**,首次启动可能要修 1-10 行
7. 从本文件"下次接着做" Step 1 开始

## Day 03 数据

| 项 | 值 |
|---|---|
| 新增文件 | 6 |
| 修改文件 | 2(main.py + mcp_server.py) |
| 新增代码行数 | ~900 |
| 累计代码行数(Python) | ~1800 |
| 累计 dream 文件总数 | 39 |
| Sleep 5 prompt 模板 | ✅ 完整 |
| StateGraph 8 节点 | ✅ 完整 |
| Staging swap | ✅ 完整 |
| APScheduler 双 trigger | ✅ 完整 |
| Activity 联动 | ✅ 完整 |
| **能跑** | ❌(等环境) |
| **prompt 质量** | 待验证(等 LLM) |
