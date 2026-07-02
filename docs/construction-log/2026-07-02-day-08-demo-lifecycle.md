# 施工记录 — 2026-07-02 Day 08: Demo 生命周期收口

## 本次目标

把 demo 从“若干脚本手动串起来”收敛成完整生命周期:准备数据、跑 Sleep、查看结果、清理 demo 数据。这样最终人工验证只需要按清单操作,不用在开发过程中频繁打断。

## 已完成

- [x] `src/mneme/demo_seed.py` 支持 demo-tagged facts 写入。
- [x] `seed_demo_memory.py --cleanup --yes` 支持 soft-delete demo seed 数据。
- [x] 去重只看 active facts,清理后可以再次 seed。
- [x] 新增 `src/mneme/demo_cycle.py`:可选 seed,强制本轮 `sleep_min_archival_count=0`,运行 Sleep,然后输出 memory snapshot。
- [x] 新增 `scripts/run_demo_cycle.py`:一条命令完成 seed + Sleep + inspect。
- [x] 新增正式 `LICENSE` 文件,README license badge 从 planned 改为 MIT。
- [x] README / QUICKSTART / DEMO / FINAL_VERIFICATION 同步最新 demo 流程。

## 新增命令

准备 demo facts:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --yes
```

一键 demo:

```bash
/Users/mac/.local/bin/uv run python scripts/run_demo_cycle.py --seed --yes
```

清理 demo facts:

```bash
/Users/mac/.local/bin/uv run python scripts/seed_demo_memory.py --cleanup --yes
```

## 关键决策

### 1. Demo facts 必须显式确认

所有写库操作都要求 `--yes`,避免开发时误把 demo 数据塞进真实 memory。

### 2. 清理用 soft-delete,不物理删除

这保持 ops_log 审计链完整。面试时也能解释:forget / cleanup 不是抹除历史,而是把事实从 active memory 中移除,同时保留事件日志。

### 3. 一键 demo 不替代真实 dogfood

`run_demo_cycle.py --seed --yes` 是 rehearsal 工具。真实 demo 仍然优先使用日常 dogfood 数据;数据不够时才使用 demo-tagged facts。

## 验证

本轮最终统一验证:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```

## 剩余人工项

- [ ] 按 `docs/FINAL_VERIFICATION.md` 跑最终人工验证。
- [ ] 录制 demo 视频或准备现场 demo。
