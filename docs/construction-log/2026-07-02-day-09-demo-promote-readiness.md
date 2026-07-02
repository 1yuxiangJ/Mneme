# 施工记录 — 2026-07-02 Day 09: Demo Promote 触发条件调优

## 本次目标

做代码级调优扫描,重点找会影响最终 demo 成功率的问题。发现 demo seed facts 虽然能写入,但默认 `use_count=0`,而 Sleep promote 阶段候选条件是 `use_count >= 5 AND confidence >= 3`。这会导致“准备了 demo 数据,但 promote 仍然没有候选”。

## 已完成

- [x] `DemoFact` 增加 `use_count` 字段。
- [x] 高置信 demo facts 设置为 promotion-ready usage signal(`use_count >= 5`)。
- [x] `seed_demo_memory()` 插入 facts 后更新 `use_count` 和 `last_used_at`。
- [x] 如果 demo facts 已经存在且仍 active,再次 seed 会刷新 usage signal,避免旧版本 seed 数据停留在 `use_count=0`。
- [x] 新增 `tests/test_demo_seed.py`,约束 demo seed 至少包含 3 条 promotion-ready facts。
- [x] `docs/QUICKSTART.md` / `docs/FINAL_VERIFICATION.md` 同步说明。

## 关键决策

### 1. 不改 Sleep promote 阈值

Sleep promote 的阈值 `use_count >= 5 AND confidence >= 3` 是业务规则,不应该为了 demo 降低生产逻辑。正确做法是让 demo seed 显式模拟“这些事实已经被多次使用过”。

### 2. Demo seed 可刷新旧数据

之前如果已经运行过 seed,数据库里可能存在 `demo-seed` facts 但 `use_count=0`。本轮让 seed 对已有 active demo facts 执行刷新,保证重复运行脚本后仍能进入 promote 候选。

## 验证

本轮最终统一跑:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```
