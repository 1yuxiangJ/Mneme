# Demo 剧本

> 回家录像 / 面试现场用。5 个场景,每个 1-2 min,总 5-8 min。

---

## 准备(录像前)

- [ ] mneme service 跑起来(`uv run python -m mneme`)
- [ ] Claude Code MCP 配置好,可看到 `mcp__mneme__remember` 等 4 个 tool
- [ ] 已经跟 Claude Code 聊过一段时间,积累真实 memory;如果不足,执行 `uv run python scripts/seed_demo_memory.py --yes`
- [ ] 想省步骤时直接执行 `uv run python scripts/run_demo_cycle.py --seed --yes`
- [ ] 终端 1:`tail -f logs/mneme.log`(看实时 trace)
- [ ] 终端 2:`uv run python scripts/inspect_memory.py --limit 10`(查 memory / ops_log 用)
- [ ] OBS / QuickTime 录屏 + 鼠标光标高亮 + 字号调大

---

## 场景 1:跨 session 认识我(30s,杀手锏)

**剧本**:打开全新 Claude Code session,什么 context 都没,问个普通问题。

```
你:推荐一个 Python web 框架

Claude Code(trace 终端 1 显示):
  → 调 mcp__mneme__list_memory
  ← {"core_blocks": [...], "archival_total": 47}
  → 调 mcp__mneme__recall("Python web framework preferences")
  ← {"results": [{content: "prefers FastAPI for async APIs", ...}]}

Claude Code 回:
  根据 mneme 中记录,你是 Java backend 实习生,偏好异步,有 FastAPI 使用经验。推荐 FastAPI:...
```

**亮点**:全新 session,无 context,Claude Code 主动用 mneme "认识你"。

---

## 场景 2:实时 remember,DB 立刻看(1 min)

**剧本**:跟 Claude Code 透露新偏好,DB 立即可见。

```
你:我决定以后所有项目用 Ruff,不用 Black 了

Claude Code(trace):
  → 调 mcp__mneme__remember(
      content="prefers Ruff over Black for Python linting/formatting",
      tags=["preference", "tooling"],
      confidence=3
    )
  ← {"status": "ok", "fact_id": 142, ...}

你(终端 2):
  uv run python scripts/inspect_memory.py --limit 5
  → archival_facts 里出现最新 fact, recent_ops 里出现 remember 审计记录
```

**亮点**:LLM 自己判断"该 remember",写入 archival。这是 LLM-driven memory writes,不是 backend CRUD。

---

## 场景 3:切到不同 project,记忆跟着过(45s)

**剧本**:切到完全不相关的项目,验证 cross-project 工作。

```
你:cd ~/some-other-project
   [启动新 Claude Code session]
   "帮我配 lint"

Claude Code(trace):
  → 调 mcp__mneme__recall("lint configuration preferences")
  ← {"results": [{content: "prefers Ruff over Black...", ...}]}

Claude Code 回:
  根据你之前的偏好,用 Ruff。我帮你写 ruff.toml:...
```

**亮点**:这是 Claude Code 自带 CLAUDE.md / auto memory **做不到**的——project 隔离。mneme 是 cross-project user model。

---

## 场景 4:Sleep cycle "做梦"(2 min,项目灵魂)

**剧本**:用够 mneme 一阵子(archival 30+ 条),触发 Sleep cycle,看后台干啥。

```bash
# 强制触发(不等 30 min idle)
uv run python scripts/run_sleep_once.py
# 如果事实数量不足,用于 demo 时可以降低本轮门槛:
uv run python scripts/run_sleep_once.py --min-archival-count 0

# 或者一条命令完成 seed + Sleep + inspect:
uv run python scripts/run_demo_cycle.py --seed --yes

# 输出:
# {"status": "ok", "plan": ["consolidate", "promote", "reflect"],
#  "consolidate_count": 3, "promote_count": 2, "reflection_preview": "..."}
```

```bash
# 看 Sleep 干了啥
uv run python scripts/inspect_memory.py --limit 10

# recent_ops 里可以看到:
# sleep_consolidate / sleep_promote / sleep_reflect
```

```bash
# 看最新 reflection(一段自然语言)
uv run python scripts/inspect_memory.py --limit 3

# recent_ops 最新 sleep_reflect 的 after_value 是一段自然语言摘要。
```

> 如果当前 active archival facts 少于 `SLEEP_MIN_ARCHIVAL_COUNT=10`,Sleep 只跑
> `reflect` 是正常结果。Demo 要展示 promote / consolidate,优先用真实 dogfood
> 积累 10+ 条事实;数据不足时用 `seed_demo_memory.py --yes` 准备 demo-tagged facts。

**讲解 talking points**:
- **Plan phase 是 LLM 自主**决定跑哪些 phase——不是 cron + SQL update
- **Promote 是唯一改 core 的路径**——Awake 永远碰不到 core,这是 Letta paper "read-only primary"
- **Reflection 一段自然语言**——给人读,验证 memory 还准

---

## 场景 5:面试官风格 — 解释架构(2 min)

**配合**:打开 `docs/construction-log/2026-06-17-day-03-sleep-agent.md` 的架构图。

**逐层讲**:
1. **Letta paper 出处**:arxiv 2504.13171,sleep-time compute, Stateful AIME +18%
2. **Awake / Sleep 双 agent**:同一份 memory,**读写权限分离**(关键)
3. **三道保险**:
   - prompt 教 LLM 别尝试
   - `memory.store.write_core_block` 应用层 `PermissionError`
   - `core_blocks.last_writer` DB 字段自检
4. **Staging swap**:Sleep 不阻塞 Awake(Letta "anytime fashion")
5. **MCP 协议**:标准化集成,理论可接 Cursor / Cline / 自建 agent

---

## Cue cards(演示时一眼能看到)

1. 全新 session,认识我
2. 实时 remember,DB 立刻看
3. 切 project,记忆跨过去
4. Sleep cycle,reflection 看人话
5. 架构图,Letta paper,三道保险

---

## 录像后处理

- 加字幕(关键 talking points 强调)
- 切掉 LLM 响应等待时间(剪掉空白)
- 突出 trace 终端 1(LLM 决策可视化)
- 上传 YouTube unlisted 或 Loom,简历放链接

---

## 录像 vs 现场 demo 选哪个

| 场景 | 推荐 |
|---|---|
| 简历附 demo | **录像**(可控,质感高) |
| 面试现场 | **现场**(展示真实 dogfooding) |
| 项目展示 | **录像 + 现场结合**(录像演示场景 1-4,场景 5 现场讲架构) |
