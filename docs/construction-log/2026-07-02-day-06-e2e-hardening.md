# 施工记录 — 2026-07-02 Day 06: E2E Demo 闭环硬化

## 本次目标

接 Day 05 的未完成项继续做,把项目从“核心集成测试通过”推进到“真实 MCP 工具 + 手动 Sleep cycle 可演示”。重点是减少人工验证依赖:提供脚本触发 Sleep,提供脚本查看 memory / ops_log,并验证 `forget` 真实链路。

## 已完成

- [x] 新增 `src/mneme/sleep/cli.py`:封装 `run_sleep_cycle()` 为可测试 CLI 入口。
- [x] 新增 `scripts/run_sleep_once.py`:手动触发一次 Sleep cycle,输出 JSON summary。
- [x] 新增 `tests/test_sleep_cli.py`:mock Sleep cycle,验证 JSON 输出和错误退出码。
- [x] 新增 `src/mneme/memory/inspect.py`:只读收集 `core_blocks` / active `archival_facts` / recent `memory_ops_log`。
- [x] 新增 `scripts/inspect_memory.py`:命令行打印 memory 快照,减少对 DataGrip 的依赖。
- [x] 新增 `tests/test_memory_inspect.py`:验证 inspect 输出包含核心区块、archival facts 和 ops log。
- [x] 真实 MCP `forget` 通过:先用 MCP `remember` 写入临时 fact #5,再用 MCP `forget` soft-delete。
- [x] 手动 Sleep cycle 通过:`run_sleep_once.py` 返回 `status=ok`,plan 为 `["reflect"]`。
- [x] `inspect_memory.py` 验证 ops_log 出现 `sleep_reflect`。
- [x] README / QUICKSTART 同步 Day 06 状态和新脚本。

## 真实验证结果

服务健康:

```bash
curl -sS http://127.0.0.1:8000/health
# {"status":"ok","service":"mneme"}
```

Claude Code MCP 连接:

```bash
scripts/claude-mneme.sh mcp list
# mneme: http://127.0.0.1:8000/mcp (HTTP) - ✔ Connected
```

真实 `forget` smoke:

```text
临时 fact #5:MNEME_SMOKE_FORGET_20260702_TEMP_FACT
forget reason:Day 06 real MCP forget smoke cleanup
结果:active archival_facts 不再包含 #5;memory_ops_log 保留 remember + forget 审计记录
```

手动 Sleep:

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
```

返回:

```json
{
  "status": "ok",
  "abort_reason": null,
  "plan": ["reflect"],
  "consolidate_count": 0,
  "promote_count": 0,
  "demote_count": 0,
  "contradictions_count": 0
}
```

当前 archival 数量少于默认 `SLEEP_MIN_ARCHIVAL_COUNT=10`,所以 plan 只跑 `reflect` 是合理结果。

## 关键决策

### 1. 用脚本触发 Sleep,不把自动 scheduler 默认打开

自动 Sleep 已经通过 `SLEEP_SCHEDULER_ENABLED=false` 默认关闭,避免开发阶段常驻服务意外消耗 token。Day 06 增加手动触发脚本,既能 demo “会做梦”,也不会引入不可控成本。

### 2. inspect 输出 JSON,不做漂亮表格

JSON 更适合复制进施工记录、issue、面试材料,也能被后续脚本消费。DataGrip 仍然可以用,但不是验证链路的必要条件。

### 3. `forget` smoke 不删除真实用户记忆

为了避免污染真实 memory,先插入带唯一标记的临时 fact,验证后立即 soft-delete。这样既测试真实 MCP 链路,又不破坏有价值的用户画像。

## 未完成

- [ ] `uv run mypy src` 仍有历史类型标注债。
- [ ] 还需要 dogfood 积累更多真实 memory,让 Sleep 的 promote / consolidate 不只跑 reflect。
- [ ] Prompt 调优和 demo 录制还没做。

## 下次接着做

1. 先修 mypy strict 中最影响可维护性的类型错误,至少把 agent/MCP 入口类型压下来。
2. 继续 dogfood,积累超过 `SLEEP_MIN_ARCHIVAL_COUNT` 的真实 facts。
3. 再跑一次 Sleep,观察 promote / consolidate 是否会改 core blocks。
4. 根据真实输出调 `sleep/prompts.py`,准备录 demo。
