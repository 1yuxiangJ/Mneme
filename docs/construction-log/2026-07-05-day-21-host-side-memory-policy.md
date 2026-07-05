# 2026-07-05 Day 21 - Host-Side Proactive Memory Policy

## 背景

Day 20 已强化 Mneme `remember` tool description,明确长期生活偏好也应该记。但用户实测发现:

- 只有用户明确说"记一下"时,Claude Code 才调用 `remember`。
- 普通访谈里用户透露长期事实时,Claude Code 仍倾向继续追问,不主动写入。

## 根因

`remember` 是否被调用,第一判断发生在 Claude Code host 端 LLM。

MCP server 的 tool description 只能说明:

```text
这个工具能做什么、适合存什么、不适合存什么
```

但它不能稳定表达:

```text
你在普通对话里应该主动使用这个工具,不要等用户说"记一下"
```

所以只改 server-side prompt 不够。需要在 Claude Code 自己会读的全局指令里加入主动记忆策略。

## 本轮操作

更新:

```text
/Users/mac/.claude/CLAUDE.md
```

新增 "Mneme 长期记忆规则":

- 当 `mneme` MCP 工具可用时,主动维护跨会话长期记忆。
- 不要等用户明确说"记住"。
- 长期稳定事实应主动调用 `remember`。
- 范围包括:
  - 身份背景、长期目标、求职/学习方向
  - 技术栈、技能、项目经历、工程偏好
  - 沟通偏好、协作方式、回答风格偏好
  - 学习习惯、工作习惯、决策习惯
  - 长期兴趣爱好、娱乐偏好、生活习惯、放松方式
  - 稳定喜欢/不喜欢、产品偏好、审美偏好
- 临时状态、当天计划、一次性事件、短期情绪不记。
- recent/temporary 信息先追问确认是否长期稳定。
- 敏感信息保存前先确认。

## 验证

从 `/Users/mac` 目录启动非交互 Claude,不给 "记一下" 指令,只陈述长期事实:

```bash
zsh -ic 'cd /Users/mac; claude -p --allowedTools mcp__mneme__remember -- "我喜欢足球，游戏、B站和抖音基本是我长期的放松方式。请自然回应我这句话。"'
```

Claude 返回:

```text
已经记住了～下次聊球聊游戏我就能接上话了
```

随后查库:

```bash
/Users/mac/.local/bin/uv run python scripts/inspect_memory.py --limit 10
```

确认新增 archival fact:

```text
id=8
content="喜欢足球，游戏、B站和抖音是长期的主要放松方式。"
tags=["lifestyle", "entertainment", "hobby"]
confidence=3
op_type="remember"
```

## 文档同步

- `docs/ARCHITECTURE.md`:新增 Host-side 主动记忆策略说明。
- `docs/QUICKSTART.md`:说明 `/Users/mac/.claude/CLAUDE.md` 是主动记忆触发的关键配置。

## 当前结论

Mneme 主动记忆需要三层一起工作:

| 层 | 作用 |
|---|---|
| Claude global instruction | 让 host LLM 主动决定该调用 remember |
| MCP tool description | 定义 remember 的适用边界 |
| Awake prompt | Mneme 内部去重、落库、排除不该存的信息 |
