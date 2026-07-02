# 施工记录 — 2026-07-02 Day 11: 本地测试数据清理

## 本次目标

用户要求清掉测试阶段产生的数据,让本地 Mneme 数据库回到可继续真实使用的干净状态。

## 清理范围

保留真实记忆:

- `source='user-request'`:用户是 Java 后端开发,正在准备实习/校招,用 Mneme 做简历项目。
- `source='explicit-user-request'`:用户偏好直接、具体、工程化的中文解释。
- `source='mneme-session'`:本机 GitHub / Claude Code / Clash 代理环境说明。

删除测试/演示数据:

- `source='demo-seed'` 的 12 条 demo facts。
- `source='smoke-test'` / `source='local-smoke-test'` 的临时 smoke facts。
- `source='user-session'` 的 ad-hoc 测试记忆。
- 对应的 `memory_ops_log` 记录。
- 测试阶段产生的 `sleep_promote` / `sleep_reflect` 记录。

重置状态:

- `core_blocks` 全部重置为空值、`version=1`、`last_writer='sleep_agent'`。
- 保留的 3 条真实 archival facts 的 `use_count=0`, `last_used_at=NULL`。
- 删除残留 staging tables。
- 确认 `archival_facts.id` default 指向 `archival_facts_id_seq`。

## 执行后状态

```text
active_archival_facts = 3
deleted_archival_facts = 0
memory_ops_log = 3 条 remember
core_blocks = 5 个空 block,version=1
```

确认 SQL:

```sql
SELECT source, is_deleted, count(*)
FROM archival_facts
GROUP BY source, is_deleted;

SELECT op_type, actor, count(*)
FROM memory_ops_log
GROUP BY op_type, actor;
```

确认结果:

```text
explicit-user-request | false | 1
mneme-session         | false | 1
user-request          | false | 1

remember | awake_agent | 3
```
