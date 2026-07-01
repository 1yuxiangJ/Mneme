# 决策清单 — Q1-Q13(全部已拍板)

> 在 2026-06-17 会话中,用户跟 Claude Code(本 agent)经过结构化讨论,逐条拍板。如要改决策,在此追加 changelog,**不要**直接改原条目。

---

## 顶层决策

### 项目方向
**Letta-inspired memory-as-a-service for Claude Code,通过 MCP 协议接入,提供跨 project 用户画像长期记忆。**

### 语言 / 栈
- **Python**(放弃 Java 方案,理由:AI agent 生态 Python 主场,Java 是 outlier)
- 求职:**双线投**(Java backend 主 + AI agent 项目差异化)
- 本项目用 Python 没人会问"为啥不和实习对口"

### ReAct loop
**用 LangGraph,不手写。** 校招生说"自研 ReAct" 可信度低,LangGraph 是行业惯例。

---

## Q1-Q13 拍板内容

### 🔴 Q1. Memory scope:跨 project 共享还是 per-project 隔离?

**决策:只做 global memory,不做 project-scoped。**

**推翻过程**:最初推荐 hybrid(global + project),用户反问"project-scoped 的写入动机是什么?回到原对话窗口里 Claude Code 自己就能记"——一针见血。最终砍掉 project-scoped,边界:
- Project 内的事:Claude Code 自己的 CLAUDE.md + auto memory
- 跨 project:mneme 服务
- LLM 通过 system prompt 学会判断"该不该写 mneme"

---

### 🔴 Q2. Sleep agent 触发策略

**决策:Idle detection + Cron 兜底**
- 30 分钟无 Awake 调用 → 触发
- 兜底:每日 03:00 强制运行一次
- 单次:max 5 分钟 / max 50k token
- 首次保护:archival < 10 条时跳过

---

### 🔴 Q3. 并发安全方案

**决策:Staging snapshot + Atomic swap**
- Sleep 启动时 snapshot 到 staging 表
- Sleep 全程只动 staging
- Awake 全程只读/写主表
- Sleep 完成时:transaction 内合并期间新增 + rename swap

完整版(post-MVP)做行级锁。MVP 先简化。

---

### 🔴 Q4. MCP 接入方式

**决策:HTTP on `localhost:8000`**
- 不用 stdio(stdio 启动进程要拉 DB 连接,绕)
- Claude Code 配 MCP 走 HTTP endpoint
- Demo 时单独跑 service,看日志好看

---

### 🔴 Q5. MCP tools(暴露给 Claude Code 的)

**决策:4 个 tools,不多不少**

| Tool | 签名 | 用途 |
|---|---|---|
| `remember` | `(content: str, tags?: List[str], confidence?: int)` | 主动写入 |
| `recall` | `(query: str, limit?: int = 5)` | 语义检索 |
| `list_memory` | `()` | 列出 core blocks 概览 + archival 总数 |
| `forget` | `(fact_id: str, reason: str)` | 删除(soft delete) |

**没有 scope 参数**(只有 global)。**没有 `/remember` slash command**(纯 LLM-driven)。

---

### 🔴 Q6. Memory 装什么 / 跟 CLAUDE.md 关系

**决策:互补,不替代**
- CLAUDE.md = 静态、显式、git-versioned(项目约定)
- mneme = 动态、implicit、跨 session(用户画像)
- Demo 杀手锏:"上次说我喜欢 4 空格" 这种 → CLAUDE.md 不会写,但 mneme 会记

---

### 🟡 Q7. 数据模型

**决策:两层简化版**
- `core_blocks`(label, value, version, char_limit, updated_at)
- `archival_facts`(content, tags, confidence, embedding, use_count, last_used_at, ...)
- 砍掉 Letta 的 `recall_messages`(我们不存对话历史)
- 加 `memory_ops_log`(给 Sleep agent diff 用)

---

### 🟡 Q8. LLM 选型

**决策:Awake + Sleep 都用 DeepSeek-chat**(改自最初"Sleep 用 Claude Sonnet")
- **理由**:用户有 DeepSeek 额度,学生项目省钱优先
- Embedding:阿里通义 `text-embedding-v3`(1024 维,国内顺畅,见 Q11 修订)
- Demo 录制时可选 Claude Sonnet 4 切换(可选)

---

### 🟡 Q9. Sleep reflection 质量验证

**决策:人工 review + diff log**
- 每次 sleep 在 `memory_ops_log` 写入 before/after/reason
- 用户跑几天后人工看 diff 是否合理
- 不上 LLM-as-judge(MVP 简化)

---

### 🔴 Q10. User_id 处理

**决策:MVP 单用户写死**
- `user_id = "userjyx"` 硬编码
- 不做认证 / 不做隔离
- README 留 "future work: multi-user"

---

### 🔴 Q11. Embedding 模型(Day 04+ 修订:OpenAI → 阿里通义)

**决策:阿里通义 `text-embedding-v3`**(1024 维,via OpenAI-compatible dashscope 端口)

- 国内付款,**无需海外手机号 / 外区银行卡 / VPN**
- 有免费额度
- 中英双语训练,**中英混合场景精度同等或略胜 OpenAI**(MTEB / C-MTEB)
- OpenAI-compatible(LangChain `OpenAIEmbeddings` 直接接,改 base_url + model + dimensions)
- DeepSeek 不提供 embedding API,必须接外部

**备选(swap base_url + model + dimensions 即切换)**:
- OpenAI `text-embedding-3-small`(1536 维,海外用户优先)
- 智谱 `embedding-3`(2048 维,跟阿里通义并列)
- 本地 BGE-m3(免费,需下载 2GB+ 模型)

**为啥从 OpenAI 改为阿里通义**:OpenAI 申请门槛高(海外手机号 + 外区银行卡 + VPN + 封号风险);阿里通义国内顺畅;mneme 场景下精度差距 < 2%,用户感觉不到。

---

### 🔴 Q12. Memory granularity

**决策:两层并存**
- **Core blocks(5-7 个固定 label)**:`background` / `preferences` / `habits` / `skills` / `lessons_learned`
  - LLM 直接更新 value
- **Archival facts(零散 + vector)**:LLM 主动 insert
- 写入时 LLM 决定:大主题 → core block 更新;零散 → archival insert

---

### 🔴 Q13. Memory 写入触发

**决策:纯 LLM 自动(prompt-driven)**
- system prompt 教 LLM 看到 user-personal facts 主动调 `remember`
- 不做 `/remember` slash command
- 这是 LLM-driven memory writes,Letta 核心思想
- **没有这一条,项目就退化为 CRUD 平台**

---

### 🔴 Q14. Awake / Sleep 权限分离(2026-06-17 Day 02 fetch refs 后新增)

**决策:照搬 Letta sleep-time paper 的 read-only primary 模式**

- **Awake agent 只读 core_blocks + 只写 archival_facts**
- **Sleep agent 是 core_blocks 的 sole writer**(promote 是唯一从 archival → core 的路径)
- Awake 即使看到"用户表达了偏好"也只能 insert archival,不直接动 core
- 应用层强制(`core_blocks.last_writer` 字段自检)

**理由**(Day 02 fetch `https://www.letta.com/blog/sleep-time-compute` 后):
- Letta paper 显式描述:"The primary agent...cannot edit its core in-context memory. The sleep agent possesses exclusive tools to manage..."
- 边界更清晰(读写分离)
- 简历叙事更硬("严格 read-only primary 模式")
- 并发安全自动到位(只有 Sleep 写 core,无 race)

---

## 后期再说(不卡 MVP)

- Q14:数据备份策略 → MVP 用 `pg_dump` cron 每日一次
- Q15:Launch script + MCP 配置示例 → Day 02 跑通后再写
- Q16:README + 简历 bullet 终稿 → Day 07
- Q17:Demo 录像策划 → Day 07
- Q18:是否 open source → 做完再决定

---

## Changelog

- **2026-06-17**:首版,Q1-Q13 拍板。Sleep agent 模型从 Claude Sonnet 改为 DeepSeek-chat(成本考虑)。Java 方案彻底放弃改 Python。
- **2026-06-17 Day 02(fetch refs 后)**:**Q14 拍板**——照搬 Letta sleep-time paper 的 read-only primary 模式。Awake 只读 core / 只写 archival,Sleep 是 core_blocks sole writer。PLAN.md §1.3 / §3.3 / §5.1 / §5.3 / §6.1 / §7.2 / §8.2 / §8.4 / §9.2 / §15 / §17 同步更新。
- **2026-06-17 Day 04+(用户拍板)**:**Q11 修订**——Embedding provider 从 OpenAI `text-embedding-3-small`(1536 维)改为**阿里通义 `text-embedding-v3`**(1024 维,via dashscope OpenAI-compatible 端口)。理由:OpenAI 中国大陆申请门槛高(海外手机号 + 外区卡 + VPN + 封号风险);阿里通义国内顺畅 + 中英混合精度同等或更好。代码改动:`.env.example` / `config.py` / `db/schema.sql` / `db/models.py` / `llm/client.py`。文档同步:README / PLAN §10 / ARCHITECTURE 多处 1536→1024 引用。
