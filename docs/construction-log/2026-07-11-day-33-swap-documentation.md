# 2026-07-11 Day 33 - Swap Documentation Walkthrough

## 背景

`docs/ARCHITECTURE.md` 的 Node 9 原先主要是一段带注释 SQL。用户可以看到执行顺序,但不容易建立以下心智模型:

- swap 前 main / staging 分别是哪一版数据。
- 为什么新行补入后还要做字段级合并。
- 为什么改名需要 tmp 中转而不能直接 staging -> main。
- 为什么成功 Sleep 后 DataGrip 里仍有空 staging 表。
- pending logs / Refresh checkpoint 为什么必须与 swap 同事务。

## 文档改动

`docs/ARCHITECTURE.md` Node 9 改为“先讲心智模型,再对照 SQL”:

1. 用 A / B 解释 main 和 staging 两版数据。
2. 解释 `lock_timeout` 限制的是等锁时间。
3. 用 `#1/#2/#3` 例子解释 snapshot 后新行补入。
4. 用 content / use_count 例子解释字段所有权。
5. 逐步展开 `main -> tmp, staging -> main, tmp -> staging`。
6. 说明旧 main 换名成 staging 后只被 TRUNCATE,所以空表会保留。
7. 说明成功 / 失败时主表、Sleep 日志和 checkpoint 的一致性。

同时修正 atomic swap 术语说明:当前是 Core / Archival 两组表,每组各做三步 RENAME,而不是模糊的“三个表名全切换”。

## 代码影响

无。本轮只澄清现有 `atomic_swap()` 行为,不改变锁、字段合并、RENAME、TRUNCATE 或 pending ops 逻辑。

## 验证

```bash
git diff --check
```

确认 Markdown 无空白错误;无代码变更,不重复运行质量门。
