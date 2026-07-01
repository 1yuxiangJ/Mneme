# MCP Python SDK 笔记

> 来源:`https://github.com/modelcontextprotocol/python-sdk`(2026-06-17 fetch)
> 包名:`mcp[cli]`

## 1. 安装

```bash
pip install "mcp[cli]"
# 或 uv:
uv add "mcp[cli]"
```

## 2. 最小 server(单 tool)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

**关键 API**:
- `FastMCP(name)` — server 实例
- `@mcp.tool()` decorator — 把函数注册为 MCP tool
- `mcp.run()` — 启动 server(默认 stdio)

## 3. 多 tool

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Multi-Tool Server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def multiply(x: int, y: int) -> int:
    """Multiply two numbers"""
    return x * y

@mcp.tool()
def greet(name: str) -> str:
    """Generate a greeting"""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

## 4. Transport 选项

### Stdio(默认,最简)
```bash
python server.py
```

### Streamable HTTP(**mneme 选这个**)
```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

→ 访问 `http://localhost:8000/mcp`

### SSE
```python
mcp.run(transport="sse")
```

## 5. FastAPI / Starlette 集成(mneme 用)

```python
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("API Server", json_response=True)

@mcp.tool()
def calculate(a: int, b: int) -> int:
    """Add numbers"""
    return a + b

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[Mount("/mcp", app=mcp.streamable_http_app())],
    lifespan=lifespan,
)

# 启动:uvicorn server:app --reload
```

**关键**:
- `mcp.streamable_http_app()` 返回 ASGI app
- `Mount("/mcp", app=...)` 挂载到 starlette 路径
- `lifespan` context 管理 mcp session

---

## 6. mneme MVP 架构对应

### 6.1 mneme 4 个 MCP tools 模板

```python
# src/mneme/mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mneme")

@mcp.tool()
async def remember(
    content: str,
    tags: list[str] | None = None,
    confidence: int = 2,
) -> dict:
    """
    Store a fact about the user (preferences, habits, lessons learned, etc).
    Only call for cross-project user-level facts. Do not call for project-specific facts.
    """
    # 触发 Awake Agent(LangGraph) — 内部 ReAct loop
    return await awake_agent.handle_remember(content, tags, confidence)

@mcp.tool()
async def recall(query: str, limit: int = 5) -> dict:
    """Semantic search over stored memory."""
    return await awake_agent.handle_recall(query, limit)

@mcp.tool()
async def list_memory() -> dict:
    """List all core blocks + archival summary."""
    return await awake_agent.handle_list()

@mcp.tool()
async def forget(fact_id: str, reason: str) -> dict:
    """Mark a fact as forgotten."""
    return await awake_agent.handle_forget(fact_id, reason)
```

### 6.2 启动结构

```python
# src/mneme/main.py
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount
from mneme.mcp_server import mcp
from mneme.sleep_scheduler import start_sleep_scheduler

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        scheduler = start_sleep_scheduler()  # APScheduler 启动 sleep agent
        try:
            yield
        finally:
            scheduler.shutdown()

app = Starlette(
    routes=[Mount("/mcp", app=mcp.streamable_http_app())],
    lifespan=lifespan,
)
```

### 6.3 Claude Code 端配置

(Day 02 实测后补具体 JSON 配置)

预期类似:
```json
{
  "mcpServers": {
    "mneme": {
      "url": "http://localhost:8000/mcp",
      "transport": "streamable-http"
    }
  }
}
```

---

## 7. 注意事项

- ✅ tool function 用 type hint + docstring,SDK 自动生成 tool schema 给 LLM
- ✅ docstring 是 LLM 决定 "**何时调用 tool**" 的 ground truth,**必须仔细写**(尤其 `remember` 的 system prompt 等效)
- ⚠️ `FastMCP` 不是 FastAPI——名字相似但是 MCP SDK 自己的 framework
- ⚠️ stdio 模式跑 server 时会占用 stdout,不能 print 任何东西(日志改 stderr 或文件)
- ⚠️ http 模式需要 Claude Code 客户端配支持(0.2+ 版本)
