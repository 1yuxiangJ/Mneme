# 2026-07-14 Day 35 - Minimal Automated Evaluation

## 目标

为简历项目补一套最小、可重复、可解释的自动化评测,回答以下问题:

1. Remember 是否正确插入稳定 Fact 并跳过近重复。
2. 语义检索和 Awake Agent 是否找得到标准答案。
3. Sleep 是否完成 Promote、Demote、防误删和重复控制。
4. 评测能否在不污染主库的前提下自动生成完整报告。

## 实现

- `evals/minimal_dataset.json`:10 条合成 Remember 输入、5 个 Query 和 Sleep 期望。
- `src/mneme/evaluation.py`:隔离库重置、真实 Agent 链路执行、确定性评分、报告生成。
- `scripts/run_eval.py`:读取 `.env` 凭据但强制切换到 `mneme_eval`。
- 安全保护:运行时查询 `current_database()`,库名不以 `_eval` 结尾就拒绝 reset。
- 输出:
  - `evals/reports/minimal-eval-report.md`
  - `evals/reports/minimal-eval-report.json`

执行链路:

```text
reset mneme_eval
→ durable Remember queue
→ Awake ReAct worker
→ semantic Recall + Agent Recall
→ 构造 promotion usage signal
→ 仅回拨指定历史 Fact 的时间
→ real Sleep cycle
→ inspect Archival / Core / Ops Log
→ deterministic scoring
```

## 首轮评测发现的问题

首轮结果为 `28/29`,失败项是旧低信号 Fact 未 Demote。分析同时发现 Promote 的 `use_count` 被污染:

1. Remember 查重调用 `search_archival`,和 Recall 共用“命中即增加 use_count”的行为。较早写入的 Fact 会被后续 Remember 查重反复计为使用。
2. 数据库确实存在 1 条 stale candidate,但 Sleep Plan 仍跳过 Demote。

修复:

- 新增 `find_archival_duplicates`:复用语义检索但不更新 `use_count/last_used_at`;Remember 使用它,Recall 继续使用 `search_archival`。
- `stale_count > 0` 时运行时强制把 `demote` 补入 Plan;Demote LLM 仍负责 `FORGET / KEEP`。

## 重跑发现的 sequence 问题

第二轮在 reset 后插入首条 Fact 时失败:`archival_facts.id` 没有默认 sequence。根因是 atomic swap 改名后,sequence ownership 跟旧主表对象移动到了 staging;`DROP staging CASCADE` 会删除 sequence。

修复:

- `atomic_swap()` 在 RENAME 后把 default 和 sequence ownership 重新绑定到新 `archival_facts.id`。
- eval reset、本地数据 reset 和异常 `cleanup_staging()` 在清理 staging 后主动执行 sequence repair。
- 新增 PostgreSQL 集成测试:swap → cleanup staging → 再 insert 必须正常生成 ID。

## 最终实测结果

环境:`deepseek-v4-flash` + `text-embedding-v3` + 独立 `mneme_eval`。

| 指标 | 结果 |
|---|---:|
| Remember decision accuracy | 10/10,100% |
| Awake Recall@3 | 5/5,100% |
| Awake MRR | 1.000 |
| Agent Recall success | 5/5,100% |
| Post-Sleep Recall@3 / MRR | 100% / 1.000 |
| Sleep lifecycle | 4/4,100% |
| Overall deterministic checks | 29/29,100% |
| Wall time | 165.13s |

Promotion target在正式 Recall 后 `use_count=2`,评测只补 3 次显式使用到阈值 5,证明 Remember 查重不再污染信号。Sleep Plan 为 `promote / demote / core_refresh / reflect`。

## 测试边界

- 小规模合成数据、单次运行,不代表生产准确率。
- No Memory 是空库检索基线,不是答案生成质量对照实验。
- 未统计 Token/费用,因为当前 LLM wrapper 没有持久化 usage metadata。
- 后续可扩展多 profile、多轮均值/方差和独立 LLM Judge,但不属于当前简历 MVP 必需范围。

## 最终质量门

```text
API key scan: passed
ruff: All checks passed
mypy: Success: no issues found in 30 source files
pytest --run-integration: 64 passed, 1 warning
```

唯一 warning 是已有的 Starlette TestClient / httpx 弃用提示,与本轮改动无关。
