# 2026-07-05 Day 23 - Visible Memory Confirmation

## 背景

用户发现 Claude Code 已经会主动写入 Mneme,但不会告诉用户。用户只能去 DataGrip / 数据库里看,才知道某条信息是否已经被记住。

这是产品交互问题:主动长期记忆不应该静默发生。用户需要一个轻量、可见、不过度打扰的确认。

## 本轮操作

更新:

```text
/Users/mac/.claude/CLAUDE.md
```

在 Mneme 长期记忆规则中加入:

```text
写入后必须给用户一个轻量可见确认,格式类似: 我已记住:xxx。
不要长篇解释工具机制,也不要把工具调用细节展开给用户。
```

## 当前语义

Claude Code 主动调用 Mneme `remember` 后,应该自然回复:

```text
我已记住:你长期通过足球、游戏、B 站和抖音放松。
```

然后继续正常对话。

## DataGrip 行顺序说明

用户还看到 DataGrip 里 `id=9` / `id=10` 显示在上面。

这是 SQL 展示顺序问题:

- 关系型数据库表本身没有"天然行顺序"。
- 只有写了明确 `ORDER BY` 的查询,结果顺序才有语义。
- DataGrip 可能沿用当前排序、过滤、索引扫描结果,或按某一列排序展示。

如果要按写入顺序看:

```sql
SELECT *
FROM archival_facts
WHERE is_deleted = false
ORDER BY id ASC;
```

如果要看最新写入:

```sql
SELECT *
FROM archival_facts
WHERE is_deleted = false
ORDER BY id DESC;
```

## 文档同步

- `docs/ARCHITECTURE.md`:补充主动写入后需要轻量确认。
- `docs/QUICKSTART.md`:说明全局 Claude 指令包含写入确认行为。
