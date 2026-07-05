from __future__ import annotations

from mneme import mcp_server
from mneme.awake import agent as awake_agent


def test_remember_tool_description_includes_lifestyle_memory_policy():
    doc = mcp_server.remember.__doc__ or ""

    assert "hobbies" in doc
    assert "entertainment" in doc
    assert "lifestyle" in doc
    assert "temporary" in doc


def test_awake_domain_constraint_includes_lifestyle_memory_policy():
    prompt = awake_agent.SYSTEM_PROMPT

    assert "hobbies" in prompt
    assert "entertainment" in prompt
    assert "lifestyle" in prompt
    assert "temporary" in prompt
