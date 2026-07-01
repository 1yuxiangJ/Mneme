# 施工记录 — 2026-06-17 Day 02 上半: Fetch References

> 注:虽然是 Day 02,日期跟 Day 01 同天——因为 Day 01 完成后用户直接接续 fetch 部分。Day 02 下半(实际写代码)等用户回家做。

## 本次目标

- 不动环境,**只 fetch 资料** 写到 `docs/research-notes/`,给 Day 02 下半(写代码)铺路
- 4 份 references:Letta agent.py / Letta sleep-time compute / MCP Python SDK / LangGraph ReAct

## 已完成

- [x] `docs/research-notes/letta-agent-source-notes.md` — 从 raw GitHub fetch `letta/agent.py`,提取 ReAct loop / heartbeat / tool execution / memory writes / summarization / tool rules 全部核心机制
- [x] `docs/research-notes/letta-sleep-time-paper-notes.md` — 从 Letta blog + WebSearch 确认 paper:
  - **Paper**:Sleep-time Compute: Beyond Inference Scaling at Test-time(arxiv 2504.13171)
  - **数据**:Stateful GSM-Symbolic +13%,Stateful AIME +18%,~5x compute 节省
  - **架构**:Awake(轻量,只读 memory)+ Sleep(重量,**唯一**能改 primary memory),异步
- [x] `docs/research-notes/mcp-python-sdk-notes.md` — 从 MCP SDK README fetch,得到完整可用模板:
  - `pip install "mcp[cli]"` + `FastMCP` + `@mcp.tool()`
  - HTTP transport: `mcp.run(transport="streamable-http")` 访问 `localhost:8000/mcp`
  - FastAPI/Starlette 集成 via `Mount("/mcp", mcp.streamable_http_app())`
- [x] `docs/research-notes/langgraph-react-notes.md` — **部分 fetch 失败**(docs SPA "Redirecting" 页),通过组合:
  - Quickstart 部分内容(`init_chat_model` / `@tool` / StateGraph imports)
  - AI 模型补全(`create_react_agent` 标准用法)
  - **明确标注 "Day 02 验证"** 的项目

## 文件变更

```
新增:
  ~/dream/docs/research-notes/letta-agent-source-notes.md         (4.7 KB,基于源码)
  ~/dream/docs/research-notes/letta-sleep-time-paper-notes.md     (4.6 KB,基于 blog+search)
  ~/dream/docs/research-notes/mcp-python-sdk-notes.md             (4.9 KB,基于官方 SDK README)
  ~/dream/docs/research-notes/langgraph-react-notes.md            (5.4 KB,基于 quickstart 部分 + 补全)
  ~/dream/docs/construction-log/2026-06-17-day-02-fetch-references.md  (本文件)

修改:
  无
```

## 关键决策 / 发现

### 1. Letta Sleep-time Compute 关键启示(对 dream 架构有冲击)— ✅ 已执行(本次会话同步)

**Letta paper 的双 agent 架构**:
- Primary (Awake) = **轻量模型**(gpt-4o-mini 级),**只读** core memory
- Sleep = **重量模型**(gpt-4.1 级),**唯一**能 edit primary memory 的 agent

→ **dream 是否照搬?**

| 维度 | Letta paper | dream MVP 当前设计 | 建议 |
|---|---|---|---|
| 不同模型 | Awake 轻 + Sleep 重 | 全 DeepSeek-chat | **保持 DeepSeek 全用**(成本),写在 README 说明 |
| Awake 只读 core | ✅ | ❌ Awake 也能 insert archival,且写 core | **照搬**:Awake 只 insert archival,**core block 改动只有 Sleep 能做**——这是更纯的 Letta 设计 |
| 异步 | ✅ | ✅(staging swap) | 保持 |

→ **PLAN.md §5 数据模型 + §7 Awake / §8 Sleep 需要调整**:
- Awake `remember` tool 只往 `archival_facts` 插入
- Sleep `promote()` 把 archival 高频项 → core_blocks
- Sleep 是唯一改 `core_blocks` 的 actor

**这一改更贴合 Letta paper,简历叙事更硬**。

### 2. MCP Python SDK 用法明朗

`FastMCP` + `@mcp.tool()` decorator 模式跟 Letta tool 注册思路类似。
- HTTP transport 选 **`streamable-http`** 而不是 SSE
- 跟 FastAPI 集成靠 Starlette `Mount`
- docstring 是 LLM 决定 "**何时调用 tool**" 的 ground truth,**写 prompt 要在 docstring 里**

### 3. LangGraph 0.2/0.3 API 变化

新版本推荐 `init_chat_model` 取代直接 ChatOpenAI。但 MVP 用直接 ChatOpenAI(更稳)。

### 4. LangGraph docs 抓取失败 = SPA 加载问题

LangGraph docs 是 Mintlify / 类似 SPA,WebFetch 拿不到 JS 渲染内容。
**Day 02 验证 LangGraph 时直接 `pip show langgraph` + 读 Python 包内 docstring** 更可靠。

## 未完成 / 阻塞

### 阻塞(等用户回家做)

- [ ] 装本地 PostgreSQL 16 + pgvector
- [ ] 注册 OpenAI 拿 embedding key(`text-embedding-3-small`)
- [ ] 复制 `.env.example` → `.env` 填值
- [ ] `uv sync` 或 `pip install -e .` 装依赖
- [ ] Claude Code 端配 MCP server(回家后实测)

### 软待办(本次没做)

- [ ] Fetch arxiv 2504.13171 完整论文(blog 已足够 MVP,后续如需 BibTeX 引用再 fetch)
- [ ] Letta sleep-time-compute accompanying code repo(`letta-ai/sleep-time-compute`)看实战代码

## 下次接着做(Day 02 下半,回家做)

按 Day 01-init 写的"下次接着做" Step 1-4 + 本次新增:

### Step 0(新增).PLAN.md 微调 — ✅ 已完成(本次会话同步执行)

**用户决定立刻照搬 Letta**,已执行调整:
- ✅ Awake `remember` 只写 archival,**不直接动 core_blocks**
- ✅ Sleep `promote()` 是唯一改 core_blocks 的路径
- ✅ PLAN.md §1.3 / §3.3 / §5.1 / §5.3 / §6.1 / §7.2 / §8.2 / §8.4 / §9.2 / §15 全部更新
- ✅ PLAN.md §17 加 changelog
- ✅ DECISIONS.md 加 **Q14** + changelog
- ✅ memory `project_resume_agent_search_2026-06.md` changelog 加 Day 02 一段

### Step 1. 环境准备(15-30 min,见 Day 01-init)

### Step 2. Hello World(Day 01-init 已写)

### Step 3. MCP Server 框架(参考 `mcp-python-sdk-notes.md`)

### Step 4. Awake Agent(参考 `langgraph-react-notes.md`)

## 接续指引(给新窗口的 Claude 看)

如果你是新窗口的 Claude,接到 "继续 dream 项目" 指令:

1. 读 `~/dream/README.md`
2. 读 `~/dream/docs/PLAN.md`
3. 读 `~/dream/docs/DECISIONS.md`
4. 读本目录**最新**施工记录(本文件就是当前最新)
5. **先看本文件 §"关键决策"第 1 条** — 那里有对 PLAN.md 的修正建议
6. 然后从"下次接着做" Step 0 开始

## Day 02 下半:用户回家后告诉新窗口 Claude 这句话即可

> 接续 `~/dream` 项目。先按 `docs/construction-log/2026-06-17-day-02-fetch-references.md` 的"下次接着做"做 Step 0(调整 PLAN.md),然后 Step 1 环境准备(我已经做完),然后 Step 2 hello world。
