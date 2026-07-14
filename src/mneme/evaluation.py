"""Minimal, reproducible evaluation harness for Mneme's memory lifecycle."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from mneme import mcp_server
from mneme.awake.tools import search_archival
from mneme.config import settings
from mneme.db.models import dispose_engine, get_engine, get_sessionmaker
from mneme.memory.store import semantic_search_archival
from mneme.memory.worker import process_one_job
from mneme.sleep.agent import run_sleep_cycle
from mneme.sleep.staging import ensure_archival_id_sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = ROOT / "evals" / "minimal_dataset.json"
DEFAULT_REPORT_DIR = ROOT / "evals" / "reports"
SCHEMA_PATH = ROOT / "src" / "mneme" / "db" / "schema.sql"
CORE_LABELS = (
    "background",
    "preferences",
    "habits",
    "skills",
    "lessons_learned",
)


class EvalFact(BaseModel):
    key: str
    content: str
    tags: list[str]
    confidence: int
    stability: str
    salience: int
    expected_store: bool
    duplicate_of: str | None = None
    backdate_days: int | None = None


class EvalQuery(BaseModel):
    key: str
    query: str
    relevant_fact_key: str
    expected_terms: list[str]
    minimum_term_matches: int = 1


class PromotionProbe(BaseModel):
    fact_key: str
    query: str
    minimum_use_count: int
    target_core_block: str
    expected_core_terms: list[str]


class DemoteExpectations(BaseModel):
    should_delete: list[str]
    should_retain: list[str]


class EvalDataset(BaseModel):
    name: str
    description: str
    facts: list[EvalFact]
    queries: list[EvalQuery]
    promotion_probe: PromotionProbe
    demote_expectations: DemoteExpectations


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> EvalDataset:
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def score_rankings(
    rankings: dict[str, list[str]],
    queries: list[EvalQuery],
) -> dict[str, Any]:
    hits = 0
    reciprocal_rank_sum = 0.0
    details: list[dict[str, Any]] = []
    for query in queries:
        ranked_keys = rankings.get(query.key, [])
        rank = next(
            (
                index + 1
                for index, key in enumerate(ranked_keys)
                if key == query.relevant_fact_key
            ),
            None,
        )
        if rank is not None and rank <= 3:
            hits += 1
            reciprocal_rank_sum += 1.0 / rank
        details.append({
            "query_key": query.key,
            "relevant_fact_key": query.relevant_fact_key,
            "rank": rank,
            "top3": ranked_keys[:3],
            "hit_at_3": rank is not None and rank <= 3,
        })
    total = len(queries)
    return {
        "hits": hits,
        "total": total,
        "recall_at_3": hits / total if total else 0.0,
        "mrr": reciprocal_rank_sum / total if total else 0.0,
        "details": details,
    }


def _schema_statements() -> list[str]:
    uncommented = "\n".join(
        line
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )
    return [statement.strip() for statement in uncommented.split(";") if statement.strip()]


async def reset_eval_database() -> str:
    """Create schema and clear data, refusing to touch a non-eval database."""
    engine = get_engine()
    async with engine.begin() as connection:
        database_name = str((await connection.execute(text(
            "SELECT current_database()"
        ))).scalar_one())
        if not database_name.endswith("_eval"):
            raise RuntimeError(
                f"Refusing to reset database {database_name!r}; name must end with '_eval'."
            )
        for statement in _schema_statements():
            await connection.exec_driver_sql(statement)
        await connection.execute(text("DROP TABLE IF EXISTS core_blocks_staging CASCADE"))
        await connection.execute(text("DROP TABLE IF EXISTS archival_facts_staging CASCADE"))
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        await ensure_archival_id_sequence(session)
        await session.commit()
    async with engine.begin() as connection:
        await connection.execute(text(
            "TRUNCATE archival_facts, memory_ops_log, memory_write_jobs RESTART IDENTITY"
        ))
        await connection.execute(text(
            "ALTER SEQUENCE archival_facts_id_seq RESTART WITH 1"
        ))
        await connection.execute(text("DELETE FROM core_blocks"))
        for label in CORE_LABELS:
            await connection.execute(text(
                "INSERT INTO core_blocks "
                "(label, value, char_limit, version, last_writer, updated_at) "
                "VALUES (:label, '', 2000, 1, 'sleep_agent', now())"
            ), {"label": label})
    return database_name


async def _job_state(job_id: int) -> dict[str, Any]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        row = (await session.execute(text(
            "SELECT status, attempt_count, last_error, result "
            "FROM memory_write_jobs WHERE id = :job_id"
        ), {"job_id": job_id})).mappings().one()
    return dict(row)


async def _run_remember(fact: EvalFact) -> dict[str, Any]:
    accepted = await mcp_server.remember(
        fact.content,
        fact.tags,
        fact.confidence,
        fact.stability,
        fact.salience,
    )
    job_id = int(accepted["job_id"])
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = await _job_state(job_id)
        if state["status"] in {"succeeded", "failed"}:
            return {"accepted": accepted, "job": state}
        await process_one_job()
        state = await _job_state(job_id)
        if state["status"] in {"succeeded", "failed"}:
            return {"accepted": accepted, "job": state}
        await _sleep(1.0)
    return {"accepted": accepted, "job": await _job_state(job_id)}


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def _load_fact_rows() -> list[dict[str, Any]]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        rows = (await session.execute(text(
            "SELECT id, content, is_deleted, use_count, last_used_at, created_at "
            "FROM archival_facts ORDER BY id"
        ))).mappings().all()
    return [dict(row) for row in rows]


async def _load_core() -> dict[str, str]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        rows = (await session.execute(text(
            "SELECT label, value FROM core_blocks ORDER BY label"
        ))).all()
    return {str(row.label): str(row.value) for row in rows}


async def _load_ops() -> list[dict[str, Any]]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        rows = (await session.execute(text(
            "SELECT id, op_type, actor, target_kind, target_id, reason, ts "
            "FROM memory_ops_log ORDER BY id"
        ))).mappings().all()
    return [dict(row) for row in rows]


async def _apply_eval_time_offsets(dataset: EvalDataset) -> None:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        for fact in dataset.facts:
            if fact.backdate_days is None:
                continue
            await session.execute(text(
                "UPDATE archival_facts "
                "SET created_at = now() - make_interval(days => :days), "
                "last_used_at = NULL "
                "WHERE content = :content"
            ), {"days": fact.backdate_days, "content": fact.content})
        await session.commit()


def _content_key_map(dataset: EvalDataset) -> dict[str, str]:
    return {fact.content: fact.key for fact in dataset.facts}


async def _rank_queries(dataset: EvalDataset, limit: int = 3) -> dict[str, list[str]]:
    content_to_key = _content_key_map(dataset)
    rankings: dict[str, list[str]] = {}
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        for query in dataset.queries:
            rows = await semantic_search_archival(session, query.query, limit=limit)
            rankings[query.key] = [
                content_to_key.get(row.content, f"unmapped:{row.id}")
                for row in rows
            ]
    return rankings


async def _run_agent_recalls(dataset: EvalDataset) -> dict[str, Any]:
    passed = 0
    details: list[dict[str, Any]] = []
    for query in dataset.queries:
        result = await mcp_server.recall(query.query, limit=3)
        message = str(result.get("final_message", ""))
        lowered = message.casefold()
        matched_terms = [term for term in query.expected_terms if term.casefold() in lowered]
        success = (
            result.get("status") == "ok"
            and len(matched_terms) >= query.minimum_term_matches
        )
        passed += int(success)
        details.append({
            "query_key": query.key,
            "status": result.get("status"),
            "matched_terms": matched_terms,
            "required_matches": query.minimum_term_matches,
            "passed": success,
            "response": message,
        })
    total = len(dataset.queries)
    return {
        "passed": passed,
        "total": total,
        "success_rate": passed / total if total else 0.0,
        "details": details,
    }


async def _prepare_promotion_signal(dataset: EvalDataset) -> dict[str, Any]:
    probe = dataset.promotion_probe
    fact_by_key = {fact.key: fact for fact in dataset.facts}
    target = fact_by_key[probe.fact_key]

    rows = await _load_fact_rows()
    current = next((row for row in rows if row["content"] == target.content), None)
    before = int(current["use_count"]) if current is not None else 0
    calls = max(0, probe.minimum_use_count - before)
    for _ in range(calls):
        await search_archival.ainvoke({"query": probe.query, "limit": 1})

    rows = await _load_fact_rows()
    current = next((row for row in rows if row["content"] == target.content), None)
    after = int(current["use_count"]) if current is not None else 0
    return {"fact_key": probe.fact_key, "before": before, "after": after, "calls": calls}


def _score_remember(dataset: EvalDataset, rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_contents = {str(row["content"]) for row in rows if not row["is_deleted"]}
    facts_by_key = {fact.key: fact for fact in dataset.facts}
    correct = 0
    details: list[dict[str, Any]] = []
    for fact in dataset.facts:
        stored = fact.content in active_contents
        duplicate_source_present = (
            fact.duplicate_of is None
            or facts_by_key[fact.duplicate_of].content in active_contents
        )
        passed = stored == fact.expected_store and duplicate_source_present
        correct += int(passed)
        details.append({
            "fact_key": fact.key,
            "expected_store": fact.expected_store,
            "stored": stored,
            "duplicate_source_present": duplicate_source_present,
            "passed": passed,
        })
    total = len(dataset.facts)
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "details": details,
    }


def _fact_state_by_key(
    dataset: EvalDataset,
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    content_to_key = _content_key_map(dataset)
    return {
        content_to_key[str(row["content"])]: row
        for row in rows
        if str(row["content"]) in content_to_key
    }


def _score_sleep(
    dataset: EvalDataset,
    rows: list[dict[str, Any]],
    core: dict[str, str],
    ops: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key = _fact_state_by_key(dataset, rows)
    probe = dataset.promotion_probe
    target_value = core.get(probe.target_core_block, "")
    core_terms = [
        term for term in probe.expected_core_terms if term.casefold() in target_value.casefold()
    ]
    promote_op_present = any(op["op_type"] == "sleep_promote" for op in ops)
    promotion_passed = len(core_terms) == len(probe.expected_core_terms) and promote_op_present

    delete_details = []
    for key in dataset.demote_expectations.should_delete:
        deleted = bool(by_key.get(key, {}).get("is_deleted", False))
        delete_details.append({"fact_key": key, "deleted": deleted, "passed": deleted})
    retain_details = []
    for key in dataset.demote_expectations.should_retain:
        row = by_key.get(key)
        retained = row is not None and not bool(row["is_deleted"])
        retain_details.append({"fact_key": key, "retained": retained, "passed": retained})

    fact_by_key = {fact.key: fact for fact in dataset.facts}
    duplicate_pairs = [fact for fact in dataset.facts if fact.duplicate_of is not None]
    duplicate_details = []
    for duplicate in duplicate_pairs:
        source = fact_by_key[duplicate.duplicate_of or ""]
        active_count = sum(
            1
            for content in (source.content, duplicate.content)
            if any(row["content"] == content and not row["is_deleted"] for row in rows)
        )
        duplicate_details.append({
            "source_key": source.key,
            "duplicate_key": duplicate.key,
            "active_count": active_count,
            "passed": active_count == 1,
        })

    checks = [
        promotion_passed,
        *(item["passed"] for item in delete_details),
        *(item["passed"] for item in retain_details),
        *(item["passed"] for item in duplicate_details),
    ]
    passed = sum(bool(check) for check in checks)
    return {
        "passed": passed,
        "total": len(checks),
        "accuracy": passed / len(checks) if checks else 0.0,
        "promotion": {
            "target_block": probe.target_core_block,
            "matched_terms": core_terms,
            "expected_terms": probe.expected_core_terms,
            "promote_op_present": promote_op_present,
            "passed": promotion_passed,
            "core_value": target_value,
        },
        "demote_should_delete": delete_details,
        "demote_should_retain": retain_details,
        "duplicate_control": duplicate_details,
    }


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    before = metrics["retrieval_before_sleep"]
    after = metrics["retrieval_after_sleep"]
    remember = metrics["remember"]
    agent = metrics["agent_recall"]
    lifecycle = metrics["sleep_lifecycle"]
    overall = metrics["overall"]
    core_available = "Yes" if lifecycle["promotion"]["passed"] else "No"
    promotion_status = "PASS" if lifecycle["promotion"]["passed"] else "FAIL"
    demote_status = (
        "PASS"
        if all(item["passed"] for item in lifecycle["demote_should_delete"])
        else "FAIL"
    )
    retain_status = (
        "PASS"
        if all(item["passed"] for item in lifecycle["demote_should_retain"])
        else "FAIL"
    )
    duplicate_status = (
        "PASS"
        if all(item["passed"] for item in lifecycle["duplicate_control"])
        else "FAIL"
    )
    lines = [
        "# Mneme Minimal Eval Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Dataset: `{report['dataset']['name']}`",
        f"- Database: `{report['database']}` (isolated eval database)",
        f"- LLM: `{report['runtime']['llm_model']}`",
        f"- Embedding: `{report['runtime']['embedding_model']}`",
        f"- Wall time: `{report['runtime']['wall_time_seconds']:.2f}s`",
        "",
        "## Executive Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        (
            f"| Remember decision accuracy | {remember['correct']}/{remember['total']} "
            f"({_percent(remember['accuracy'])}) |"
        ),
        (
            f"| Awake retrieval Recall@3 | {before['hits']}/{before['total']} "
            f"({_percent(before['recall_at_3'])}) |"
        ),
        f"| Awake retrieval MRR | {before['mrr']:.3f} |",
        (
            f"| Agent Recall success | {agent['passed']}/{agent['total']} "
            f"({_percent(agent['success_rate'])}) |"
        ),
        (
            f"| Post-Sleep retrieval Recall@3 | {after['hits']}/{after['total']} "
            f"({_percent(after['recall_at_3'])}) |"
        ),
        f"| Post-Sleep retrieval MRR | {after['mrr']:.3f} |",
        (
            f"| Sleep lifecycle checks | {lifecycle['passed']}/{lifecycle['total']} "
            f"({_percent(lifecycle['accuracy'])}) |"
        ),
        (
            f"| Overall deterministic checks | {overall['passed']}/{overall['total']} "
            f"({_percent(overall['accuracy'])}) |"
        ),
        "",
        "## Method",
        "",
        (
            "The harness resets an isolated `_eval` PostgreSQL database, submits every "
            "input through the real durable Remember queue and Awake ReAct worker, runs "
            "semantic and Agent Recall, simulates age only by backdating the designated "
            "historical fact, executes one real Sleep cycle, and scores the resulting "
            "Archival/Core/Ops Log state against deterministic expectations."
        ),
        "",
        (
            "The no-memory control has Recall@3 = 0 because the same isolated database "
            "is empty before ingestion. The primary comparison is therefore "
            "`No Memory -> Awake Only -> Awake + Sleep`."
        ),
        "",
        "## Comparison",
        "",
        "| Mode | Recall@3 | MRR | Core promotion available |",
        "|---|---:|---:|---:|",
        "| No Memory | 0.0% | 0.000 | No |",
        f"| Awake Only | {_percent(before['recall_at_3'])} | {before['mrr']:.3f} | No |",
        (
            f"| Awake + Sleep | {_percent(after['recall_at_3'])} | "
            f"{after['mrr']:.3f} | {core_available} |"
        ),
        "",
        "## Per-query Retrieval",
        "",
        "| Query | Before rank | After rank | Agent recall |",
        "|---|---:|---:|---:|",
    ]
    agent_by_key = {item["query_key"]: item for item in agent["details"]}
    after_by_key = {item["query_key"]: item for item in after["details"]}
    for item in before["details"]:
        query_key = item["query_key"]
        lines.append(
            f"| `{query_key}` | {item['rank'] or '-'} | "
            f"{after_by_key[query_key]['rank'] or '-'} | "
            f"{'PASS' if agent_by_key[query_key]['passed'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "## Sleep Lifecycle",
        "",
        (
            f"- Promotion: `{promotion_status}`; block "
            f"`{lifecycle['promotion']['target_block']}`; matched terms "
            f"`{', '.join(lifecycle['promotion']['matched_terms'])}`."
        ),
        f"- Demote old low-signal fact: `{demote_status}`.",
        f"- Retain recent low-signal fact: `{retain_status}`.",
        f"- Duplicate active-copy invariant: `{duplicate_status}`.",
        (
            f"- Sleep status: `{report['sleep_result']['status']}`; plan: "
            f"`{', '.join(report['sleep_result'].get('plan', []))}`."
        ),
        "",
        "## Limitations",
        "",
        (
            "- This is a deliberately small synthetic benchmark, not a statistically "
            "representative production benchmark."
        ),
        (
            "- One run cannot quantify LLM variance; temperature is 0, but provider "
            "behavior may still vary."
        ),
        (
            "- The no-memory control is deterministic empty retrieval rather than a "
            "separately judged answer-generation benchmark."
        ),
        (
            "- Token usage is not reported because the current LLM wrapper does not "
            "persist provider usage metadata."
        ),
        "",
        "Full case-level evidence is available in the adjacent JSON report.",
        "",
    ])
    return "\n".join(lines)


async def run_minimal_eval(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    started = time.monotonic()
    dataset = load_dataset(dataset_path)
    database_name = await reset_eval_database()

    remember_jobs = []
    for fact in dataset.facts:
        outcome = await _run_remember(fact)
        remember_jobs.append({
            "fact_key": fact.key,
            "job_id": outcome["accepted"]["job_id"],
            "status": outcome["job"]["status"],
            "attempt_count": outcome["job"]["attempt_count"],
            "last_error": outcome["job"]["last_error"],
        })

    rows_after_remember = await _load_fact_rows()
    remember_score = _score_remember(dataset, rows_after_remember)
    rankings_before = await _rank_queries(dataset)
    retrieval_before = score_rankings(rankings_before, dataset.queries)
    agent_recall = await _run_agent_recalls(dataset)
    promotion_signal = await _prepare_promotion_signal(dataset)
    await _apply_eval_time_offsets(dataset)

    previous_minimum = settings.sleep_min_archival_count
    settings.sleep_min_archival_count = 0
    try:
        sleep_result = await run_sleep_cycle()
    finally:
        settings.sleep_min_archival_count = previous_minimum

    rows_after_sleep = await _load_fact_rows()
    core_after_sleep = await _load_core()
    ops = await _load_ops()
    rankings_after = await _rank_queries(dataset)
    retrieval_after = score_rankings(rankings_after, dataset.queries)
    lifecycle = _score_sleep(dataset, rows_after_sleep, core_after_sleep, ops)

    overall_passed = (
        remember_score["correct"]
        + retrieval_before["hits"]
        + agent_recall["passed"]
        + retrieval_after["hits"]
        + lifecycle["passed"]
    )
    overall_total = (
        remember_score["total"]
        + retrieval_before["total"]
        + agent_recall["total"]
        + retrieval_after["total"]
        + lifecycle["total"]
    )
    generated_at = datetime.now(UTC).isoformat()
    report: dict[str, Any] = {
        "generated_at": generated_at,
        "database": database_name,
        "dataset": {
            "name": dataset.name,
            "description": dataset.description,
            "fact_count": len(dataset.facts),
            "query_count": len(dataset.queries),
        },
        "runtime": {
            "llm_model": settings.deepseek_model,
            "embedding_model": settings.embed_model,
            "wall_time_seconds": time.monotonic() - started,
        },
        "metrics": {
            "no_memory": {"recall_at_3": 0.0, "mrr": 0.0},
            "remember": remember_score,
            "retrieval_before_sleep": retrieval_before,
            "agent_recall": agent_recall,
            "retrieval_after_sleep": retrieval_after,
            "sleep_lifecycle": lifecycle,
            "overall": {
                "passed": overall_passed,
                "total": overall_total,
                "accuracy": overall_passed / overall_total if overall_total else 0.0,
            },
        },
        "promotion_signal": promotion_signal,
        "sleep_result": sleep_result,
        "remember_jobs": remember_jobs,
        "core_after_sleep": core_after_sleep,
        "archival_after_sleep": rows_after_sleep,
        "ops_log": ops,
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "minimal-eval-report.json"
    markdown_path = report_dir / "minimal-eval-report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    await dispose_engine()
    return report
