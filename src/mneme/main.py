"""mneme service entrypoint.

Starlette app mounting the MCP streamable-http transport at `/mcp` plus a
`/health` endpoint. Sleep agent scheduler integration is Day 03+.

Run with:
    uv run python -m mneme            # via __main__.py
    uv run uvicorn mneme.main:app     # direct
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mneme.config import settings
from mneme.db.models import dispose_engine
from mneme.mcp_server import mcp

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mneme")


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mneme"})


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Startup + shutdown hooks."""
    logger.info("mneme startup; mcp at %s", settings.mcp_server_path)
    from mneme.sleep.scheduler import start_sleep_scheduler
    scheduler = start_sleep_scheduler()
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            logger.info("mneme shutdown")
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            await dispose_engine()


app = Starlette(
    debug=False,
    routes=[
        Route("/health", health),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)


def main() -> None:
    """Entry point for `python -m mneme`."""
    import uvicorn

    uvicorn.run(
        "mneme.main:app",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
