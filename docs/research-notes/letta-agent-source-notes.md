# Letta `letta/agent.py` 源码笔记

> 来源:WebFetch `https://raw.githubusercontent.com/letta-ai/letta/main/letta/agent.py`(2026-06-17 fetch)
> Letta repo 最新 release:**v0.16.8 (2026-05-14)**

## 1. `step()` 主循环结构

```python
while True:
    step_response = self.inner_step(...)
    step_count += 1
    total_usage += usage
    if not chaining: break
    elif max_chaining_steps reached: break
    elif [chain handlers]: continue
    else: break
```

**关键点**:
- 单个 `step()` 内部 chain 多次 `inner_step()`(每次一次 LLM call)
- `chaining` 标志 + `max_chaining_steps` 防止 unbounded loop
- 累积 usage stats(token 计费)

## 2. Heartbeat 机制(3 个触发源)

Heartbeat 触发 chaining(让 LLM 再走一轮):

| 触发源 | 何时 fire |
|---|---|
| **显式请求** | Tool 返回值里带 `"request_heartbeat": true` |
| **Tool 失败** | function call 失败,inject `FUNC_FAILED_HEARTBEAT_MESSAGE` |
| **Children tools** | 当前 tool 标记 `has_children_tools` 或 `continue_tool` → 强制下一轮 |

**实现细节**:loop 通过 inject 一个合成 user message(含 heartbeat 时间戳)继续。

## 3. Tool 执行流(`_handle_ai_response()`)

```
1. Parse LLM tool call (name + JSON args)
2. Retrieve tool definition from DB
3. Dispatch via execute_tool_and_persist_state():
   - LETTA_CORE tools  → 访问 full Agent 对象
   - Memory/sleep tools → 操作 agent_state copy,持久化 block 改动
   - Composio/MCP tools → 调外部 API
   - Sandbox tools     → 跑隔离环境
4. 校验 response 长度 ≤ tool.return_char_limit
5. 打包结果,append 为 "tool" role message
```

## 4. Memory 写入路径(关键!)

**LLM 不能直接改 memory,必须通过 tool**:
- Core memory tools 接收 `agent_state` copy
- 修改 block
- `update_memory_if_changed()` 持久化
- **Read-only block 保护**:`ensure_read_only_block_not_modified()` 抛错
- 持久化:`BlockManager.update_block()` → 重建 system prompt

→ **这是 Letta 的核心范式:LLM-driven memory writes via tool calls**

## 5. Background Summarization(`summarize_messages_inplace()`)

**触发条件**:
- LLM response token 数 > `memory_warning_threshold × context_window`(默认 80%)
- 本周期没已经 alert 过(防 spam)
- `active_memory_warning` flag 触发 chaining loop

**流程**:
1. `calculate_summarizer_cutoff()` 算 cutoff
2. 调 **独立** summarization LLM 压缩老消息
3. 把 summary prepend 为合成 user message
4. trim 原消息,reset alert flag

**失败处理**:max retries 后抛 `ContextWindowExceededError`

## 6. Tool Rules(`ToolRulesSolver`)

3 类规则:

| 规则 | 行为 |
|---|---|
| `init_tool_rules` | step_count==0 时强制特定 tool(若 structured output 不支持) |
| `is_terminal_tool()` | 调用后 disable heartbeat,loop 结束 |
| `has_children_tools()` | 调用后 force heartbeat,跑子任务 |

**额外**:
- 上一步 function 失败 → 把失败 tool 从 `allowed_tool_names` 移除
- Tool calls 记入 `tool_call_history` 做 state 转移
- Structured output 支持决定规则是否可靠执行

---

## mneme MVP 借鉴清单

| 机制 | 我们 MVP 怎么做 |
|---|---|
| `while True` step loop | LangGraph 自带 state graph,**不手写** |
| heartbeat 3 触发源 | **不做**(MVP),LangGraph 内置 loop 控制 |
| Tool 执行流 | LangChain `@tool` + LangGraph |
| LLM-driven memory writes | **必须做**——这是项目灵魂,Awake agent 必须通过 `remember` tool 写 |
| Background summarization | Sleep agent 阶段做 consolidation |
| Read-only block 保护 | MVP 简化:`memory_ops_log` 记录 + 不强制 read-only |
| Tool Rules | **不做**,system prompt 约束即可 |

**不要照抄 Letta 实现**(那是 Python 自研框架,我们用 LangGraph)。**借鉴的是 idea**:
1. Memory 写入必须经过 tool(不是 direct LLM mutation)
2. Read-only 概念
3. Summarization 在 context 满时触发(我们的 Sleep 也有类似机制)
4. Tool Rules 的 init/terminal 思路(MVP 简化为 prompt)
