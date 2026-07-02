# 施工记录 — 2026-07-02 Day 10: Sleep snapshot sequence 修复

## 本次目标

用户执行:

```bash
/Users/mac/.local/bin/uv run python scripts/run_sleep_once.py
```

终端输出大量 traceback,但数据库 `memory_ops_log` 看不到 Sleep 日志。需要定位原因并修复。

## 根因

Sleep cycle 在第一个节点 `snapshot_to_staging()` 就失败了:

```text
relation "archival_facts_id_seq" does not exist
```

当时数据库状态:

```sql
SELECT column_default
FROM information_schema.columns
WHERE table_name='archival_facts' AND column_name='id';
-- 空

SELECT relname FROM pg_class WHERE relkind='S';
-- 只有 memory_ops_log_id_seq
```

也就是说,`archival_facts.id` 的 BIGSERIAL default 已经丢失,并且 `archival_facts_id_seq` 不存在。Sleep 还没进入 plan / reflect / promote 阶段,所以不会写 `sleep_reflect` 或其他 `sleep_*` ops_log。

## 已完成

- [x] `sleep/staging.py` 新增 `_ensure_archival_id_sequence()`。
- [x] Sleep snapshot 前自动 `CREATE SEQUENCE IF NOT EXISTS archival_facts_id_seq`。
- [x] 自动按当前 `MAX(id)` 修复 sequence value。
- [x] 自动给 `archival_facts.id` 恢复 default。
- [x] 创建 `archival_facts_staging` 后也设置同一个稳定 sequence default。
- [x] 新增集成测试 `test_snapshot_repairs_missing_archival_id_sequence`:
  - 模拟主表 default 丢失
  - 删除 sequence
  - 跑 snapshot + atomic_swap
  - 验证后续 insert 能自动生成 id

## 关键决策

### 1. 不再假设 sequence 一定存在

之前代码硬编码:

```sql
nextval('archival_facts_id_seq'::regclass)
```

如果本地库已经因为历史 swap 进入坏状态,这行会直接炸。现在每次 snapshot 前都会先 repair。

### 2. 使用稳定 sequence 名

staging swap 会交换表名,但 sequence 应该作为稳定外部对象存在。主表和 staging 表都指向同一个 `archival_facts_id_seq`,swap 后新主表仍然能继续 insert。

## 验证

本轮最终统一跑:

```bash
/Users/mac/.local/bin/uv run ruff check
/Users/mac/.local/bin/uv run mypy src
/Users/mac/.local/bin/uv run pytest --run-integration
```
