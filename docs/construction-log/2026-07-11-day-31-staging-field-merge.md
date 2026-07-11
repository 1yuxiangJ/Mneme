# 2026-07-11 Day 31 - Staging Field-Level Merge

## 背景

Sleep 开始时会把主表整表复制到 staging。cycle 期间 Awake 仍然可以读写主表:

- 新 INSERT 的 fact 已由现有 `created_at > snapshot_ts` 逻辑补入 staging。
- 已有 fact 的 `use_count + 1` / `last_used_at` 更新会被 staging 里的快照旧值覆盖。
- Awake forget 和 Sleep demote 如果分别发生在主表 / staging,整行切换可能让已软删除的 fact 复活。

该问题在 `STUDY-NOTES.md` §4.4 Q3 和优化 Backlog 中已记录,但之前只完成了新行合并,未完成已有行的字段级合并。

## 决策

在 `atomic_swap()` 的同一短事务里按字段所有权合并:

| 字段 | 合并规则 |
|---|---|
| `content/tags/confidence/stability/salience/source/embedding` | 保留 staging 中 Sleep 的语义整理结果 |
| `use_count` | 两边取 `GREATEST` |
| `last_used_at` | 两边取非空的较新时间 |
| `is_deleted` | 两边做 OR,删除一旦发生就保留 |

合并前执行:

```sql
LOCK TABLE archival_facts IN SHARE ROW EXCLUSIVE MODE;
```

该锁会阻止新的 INSERT / UPDATE / DELETE,关闭“字段合并完成后、RENAME 之前又有 Awake 更新”的竞态窗口,但不阻塞普通 SELECT。RENAME 仍会短暂升级为 `ACCESS EXCLUSIVE LOCK`,并继续受 `lock_timeout=500ms` 保护。

## 代码改动

- `src/mneme/sleep/staging.py`
  - 更新 concurrency model 注释。
  - swap 前显式获取 archival 写锁。
  - 新行补入后执行已有行字段级合并。
- `tests/test_sleep_staging_unit.py`
  - 验证 lock / insert / update 在 RENAME 前的执行顺序。
- `tests/test_sleep_staging.py`
  - 真实 PostgreSQL 验证 Sleep 语义改动、Awake 访问统计和两侧软删除都能在 swap 后保留。

## 文档同步

- `docs/ARCHITECTURE.md`:更新 Node 9 swap SQL、字段所有权和锁语义。
- `docs/STUDY-NOTES.md`:将 §4.4 Q3 和优化 Backlog 标为 Day 31 已完成。
- `README.md`:移除已完成的 row-level merge Roadmap,替换为大数据量 MVCC 演进方向。

## 验证记录

定向单元 + 真实 PostgreSQL 集成测试:

```bash
/Users/mac/.local/bin/uv run pytest \
  tests/test_sleep_staging_unit.py \
  tests/test_sleep_staging.py \
  --run-integration
```

结果:

```text
11 passed
```

完整质量门:

```bash
/Users/mac/.local/bin/uv run ruff check src tests scripts
/Users/mac/.local/bin/uv run mypy src scripts
/Users/mac/.local/bin/uv run pytest --run-integration
```

结果:

```text
ruff: All checks passed
mypy: Success, no issues found in 36 source files
pytest: 50 passed, 1 warning
```

warning 为已知的 Starlette `TestClient` / `httpx` 弃用提示,与本次 staging 改动无关。
