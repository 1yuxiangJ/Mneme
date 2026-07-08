# 2026-07-08 Day 30 - Staging Table Documentation Correction

## 背景

用户在 DataGrip 里看到:

```text
core_blocks_staging
archival_facts_staging
```

并追问 staging 表不是应该被删除吗。

排查数据库:

```text
core_blocks_staging: 0 rows
archival_facts_staging: 0 rows
```

排查代码后确认当前实现语义:

- `snapshot_to_staging()` 开始时会 `DROP TABLE IF EXISTS *_staging CASCADE`,再重新创建 staging。
- `atomic_swap()` 成功后通过三步 `RENAME` 交换 main / staging。
- 交换后原 main 会被改名成新的 staging,然后被 `TRUNCATE` 清空。
- `cleanup_staging()` 只在 aborted / missing snapshot / 显式清理测试时真正 `DROP` staging。

因此成功 Sleep cycle 后看到空 staging 表是当前代码预期行为,不是脏数据。

## 修正

`docs/ARCHITECTURE.md` 原先写成:

```text
Sleep cycle 启动时建,跑完 swap,cleanup 时删。
```

这会让人误以为成功 swap 后 staging 表一定消失。

已改为:

```text
成功 atomic_swap 后 staging 表会保留,但应该是空表。
cleanup_staging() 只在 aborted / missing snapshot_ts / 显式清理测试时执行。
下次 snapshot 开始仍会先 DROP TABLE IF EXISTS *_staging CASCADE。
```

## 代码影响

无代码改动。当前实现和测试一致:

- `tests/test_sleep_staging.py::test_atomic_swap_replaces_main` 断言 swap 后 staging 表存在且为空。
- `tests/test_sleep_staging.py::test_cleanup_staging_drops_tables` 单独验证 cleanup 会 drop staging。
