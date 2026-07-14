from __future__ import annotations

from mneme.evaluation import EvalQuery, render_markdown_report, score_rankings


def test_score_rankings_calculates_recall_at_3_and_mrr():
    queries = [
        EvalQuery(
            key="q1",
            query="first",
            relevant_fact_key="a",
            expected_terms=["a"],
        ),
        EvalQuery(
            key="q2",
            query="second",
            relevant_fact_key="b",
            expected_terms=["b"],
        ),
    ]

    score = score_rankings(
        {"q1": ["x", "a", "z"], "q2": ["x", "y", "z"]},
        queries,
    )

    assert score["hits"] == 1
    assert score["recall_at_3"] == 0.5
    assert score["mrr"] == 0.25


def test_render_markdown_report_includes_headline_metrics():
    retrieval = {
        "hits": 1,
        "total": 1,
        "recall_at_3": 1.0,
        "mrr": 1.0,
        "details": [{"query_key": "q", "rank": 1}],
    }
    report = {
        "generated_at": "2026-07-14T00:00:00+00:00",
        "database": "mneme_eval",
        "dataset": {"name": "test"},
        "runtime": {
            "llm_model": "deepseek-chat",
            "embedding_model": "text-embedding-v3",
            "wall_time_seconds": 1.0,
        },
        "metrics": {
            "remember": {"correct": 1, "total": 1, "accuracy": 1.0},
            "retrieval_before_sleep": retrieval,
            "retrieval_after_sleep": retrieval,
            "agent_recall": {
                "passed": 1,
                "total": 1,
                "success_rate": 1.0,
                "details": [{"query_key": "q", "passed": True}],
            },
            "sleep_lifecycle": {
                "passed": 4,
                "total": 4,
                "accuracy": 1.0,
                "promotion": {
                    "passed": True,
                    "target_block": "preferences",
                    "matched_terms": ["concise"],
                },
                "demote_should_delete": [{"passed": True}],
                "demote_should_retain": [{"passed": True}],
                "duplicate_control": [{"passed": True}],
            },
            "overall": {"passed": 8, "total": 8, "accuracy": 1.0},
        },
        "sleep_result": {"status": "ok", "plan": ["promote", "demote"]},
    }

    rendered = render_markdown_report(report)

    assert "Remember decision accuracy" in rendered
    assert "Recall@3" in rendered
    assert "8/8" in rendered
