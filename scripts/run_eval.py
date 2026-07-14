#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values


def _default_eval_database_url() -> str:
    configured = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get(
        "DATABASE_URL"
    )
    if not configured:
        raise RuntimeError("DATABASE_URL is missing from .env")
    parts = urlsplit(str(configured))
    return urlunsplit(parts._replace(path="/mneme_eval"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Mneme's isolated minimal memory evaluation.",
    )
    parser.add_argument(
        "--database-url",
        help="Evaluation DB URL; defaults to .env credentials with database mneme_eval.",
    )
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = args.database_url or _default_eval_database_url()

    from mneme.evaluation import run_minimal_eval

    report = asyncio.run(run_minimal_eval())
    overall = report["metrics"]["overall"]
    print(
        "Mneme eval complete: "
        f"{overall['passed']}/{overall['total']} checks passed; "
        "report=evals/reports/minimal-eval-report.md"
    )
    return 0 if report["sleep_result"].get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
