"""CLI helpers for manually triggering Sleep cycles."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mneme.sleep.agent import run_sleep_cycle


async def run_once() -> int:
    """Run one Sleep cycle and print a JSON summary."""
    result: dict[str, Any] = await run_sleep_cycle()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result.get("status") == "error" else 0


def main() -> int:
    return asyncio.run(run_once())
