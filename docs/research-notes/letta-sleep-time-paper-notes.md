# Letta Sleep-time Compute 笔记

> 来源:
> - Blog:`https://www.letta.com/blog/sleep-time-compute`(2026-06-17 fetch)
> - Paper:**Sleep-time Compute: Beyond Inference Scaling at Test-time**(Letta + UC Berkeley,arxiv 2504.13171)
> - Accompanying code:`https://github.com/letta-ai/sleep-time-compute`

## 1. 问题陈述

传统 AI 系统**只在 user 交互时**激活推理,大量 idle 时间被浪费。
**Stateless 模型**不能利用 downtime,因为"any insights made during downtime would simply vanish when the next interaction begins"。
→ **Sleep-time compute 必须基于 stateful agent**(有 persistent memory)。

## 2. Sleep Agent 实际做什么

**Reorganizes information by rewriting memory state**。具体:

| 操作 | 描述 |
|---|---|
| **Reorganize raw context → "learned context"** | 把原始/零散的信息整理成结构化的 learned knowledge |
| **Parse uploaded documents** | 后台解析文档(用户提供的) |
| **Generate clean, concise memory** | 通过持续 refinement(非简单累积)产出干净的 memory |

**关键 quote**:"continuous refinement rather than incremental accumulation"
→ Sleep agent 不是简单 append,是**重写 / 提炼**。

## 3. Awake / Sleep Agent 交互

**关键架构**:

| Agent | 角色 | Model |
|---|---|---|
| **Primary (Awake)** | 处理 user 对话 + tool calls | **轻量 + 快**(GPT-4o-mini) |
| **Sleep** | 管理 memory(包括 primary 的 memory) | **重量 + 慢**(GPT-4.1) |

**关键 quote**:
> "The primary agent handles user conversations and tool calls **but cannot edit its core in-context memory**. The sleep agent possesses exclusive tools to manage **both its own memory and the primary agent's memory**."

> "This happens in an **'anytime' fashion** - so the primary agent can read from this memory whenever, without having to wait."

**含义**:
- Primary 是 **只读** 自己的 core memory
- Sleep 是**唯一**能 edit primary memory 的 agent
- 异步,primary 不阻塞

## 4. 论文指标

| 指标 | 数值 |
|---|---|
| Stateful GSM-Symbolic 准确率提升 | **+13%** |
| Stateful AIME 准确率提升 | **+18%** |
| Test-time compute 减少 | **~5x lower**(same accuracy) |

数据集:**Stateful AIME** + **Stateful GSM-Symbolic**(论文新提出)

## 5. mneme MVP 怎么借鉴

### 5.1 完全照搬的思路

- ✅ **双 agent 架构**:Awake + Sleep
- ✅ **异步**:Sleep 后台跑,不阻塞 Awake
- ✅ **Sleep 是唯一改 memory 的**(Awake 通过 tool 触发,但 Sleep 才真正重组)
  - 注:MVP 简化版,Awake 也直接 insert archival,**但 core block 由 Sleep promote**
- ✅ **Reorganize / refinement(非累积)**:Sleep 做 consolidation 是重写,不是 append

### 5.2 MVP 简化点

- ❌ **不同 LLM 模型** Letta 用 mini + 4.1 我们都用 DeepSeek(成本)
- ❌ **"Anytime" 异步** MVP:Sleep 跑 staging,完成后 atomic swap(简化版异步)
- ❌ **Document parsing** MVP 不做(没有 user 上传文档场景)

### 5.3 简历叙事可引用

> "参考 Letta 团队 2026 年 sleep-time compute paper (arxiv 2504.13171),实现 Awake + Sleep 双 agent 架构。Sleep agent 在 idle 时执行 consolidation / promotion / reflection,通过 staging snapshot + atomic swap 保证并发安全。论文报告该范式在 stateful 推理任务上 +13~18% 准确率,~5x compute 节省。"

→ **简历杀器**:引用论文 + 实现核心机制 + 给数据。

---

## 6. mneme Sleep Agent 任务清单(基于 paper)

| Letta 描述 | mneme 对应 |
|---|---|
| reorganize raw → learned context | `consolidate_archival_facts()`:相似 facts 合并 |
| continuous refinement | `promote()`:archival 反复用 → 提升到 core block |
| generate clean concise memory | `reflect()`:Sleep 输出"about user" 短摘要 |
| manage primary agent's memory | `update_core_block()`:Sleep 修 core(Awake 只读) |
| (not in paper, mneme 自加) | `demote()`:stale memory 降级或删 |
| (not in paper, mneme 自加) | `resolve_conflict()`:发现矛盾 fact 主动修复 |

---

## 7. 论文引用(简历 / README 用)

```
@article{packer2025sleeptime,
  title={Sleep-time Compute: Beyond Inference Scaling at Test-time},
  author={Packer, Charles and ...},  # 待确认完整作者列表
  journal={arXiv preprint arXiv:2504.13171},
  year={2025}
}
```

(完整 BibTeX Day 02 起后续 fetch arxiv 页面填充)
