# Mneme Minimal Eval Report

- Generated: `2026-07-14T13:47:43.285070+00:00`
- Dataset: `mneme-minimal-eval-v1`
- Database: `mneme_eval` (isolated eval database)
- LLM: `deepseek-v4-flash`
- Embedding: `text-embedding-v3`
- Wall time: `165.13s`

## Executive Summary

| Metric | Result |
|---|---:|
| Remember decision accuracy | 10/10 (100.0%) |
| Awake retrieval Recall@3 | 5/5 (100.0%) |
| Awake retrieval MRR | 1.000 |
| Agent Recall success | 5/5 (100.0%) |
| Post-Sleep retrieval Recall@3 | 5/5 (100.0%) |
| Post-Sleep retrieval MRR | 1.000 |
| Sleep lifecycle checks | 4/4 (100.0%) |
| Overall deterministic checks | 29/29 (100.0%) |

## Method

The harness resets an isolated `_eval` PostgreSQL database, submits every input through the real durable Remember queue and Awake ReAct worker, runs semantic and Agent Recall, simulates age only by backdating the designated historical fact, executes one real Sleep cycle, and scores the resulting Archival/Core/Ops Log state against deterministic expectations.

The no-memory control has Recall@3 = 0 because the same isolated database is empty before ingestion. The primary comparison is therefore `No Memory -> Awake Only -> Awake + Sleep`.

## Comparison

| Mode | Recall@3 | MRR | Core promotion available |
|---|---:|---:|---:|
| No Memory | 0.0% | 0.000 | No |
| Awake Only | 100.0% | 1.000 | No |
| Awake + Sleep | 100.0% | 1.000 | Yes |

## Per-query Retrieval

| Query | Before rank | After rank | Agent recall |
|---|---:|---:|---:|
| `communication_query` | 1 | 1 | PASS |
| `occupation_query` | 1 | 1 | PASS |
| `sql_query` | 1 | 1 | PASS |
| `evening_query` | 1 | 1 | PASS |
| `relaxation_query` | 1 | 1 | PASS |

## Sleep Lifecycle

- Promotion: `PASS`; block `preferences`; matched terms `concise, concrete`.
- Demote old low-signal fact: `PASS`.
- Retain recent low-signal fact: `PASS`.
- Duplicate active-copy invariant: `PASS`.
- Sleep status: `ok`; plan: `promote, demote, core_refresh, reflect`.

## Limitations

- This is a deliberately small synthetic benchmark, not a statistically representative production benchmark.
- One run cannot quantify LLM variance; temperature is 0, but provider behavior may still vary.
- The no-memory control is deterministic empty retrieval rather than a separately judged answer-generation benchmark.
- Token usage is not reported because the current LLM wrapper does not persist provider usage metadata.

Full case-level evidence is available in the adjacent JSON report.
