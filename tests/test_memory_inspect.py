from __future__ import annotations

from mneme.memory.inspect import format_snapshot


def test_format_snapshot_includes_core_archival_and_ops():
    rendered = format_snapshot({
        "core_blocks": [
            {"label": "preferences", "value": "direct answers", "version": 2}
        ],
        "archival_facts": [
            {
                "id": 3,
                "content": "likes concrete Chinese explanations",
                "tags": ["preference"],
            }
        ],
        "recent_ops": [
            {"op_type": "remember", "actor": "awake_agent", "target_id": "3"}
        ],
    })

    assert "core_blocks" in rendered
    assert "preferences" in rendered
    assert "archival_facts" in rendered
    assert "likes concrete" in rendered
    assert "recent_ops" in rendered
    assert "remember" in rendered
