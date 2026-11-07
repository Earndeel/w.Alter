"""events.compact / order (07/11): an agent finds « the first event about X » in one call, with a bounded answer."""
from walter_memory import events


def _row(i, content):
    return {"event_id": f"e{i}", "occurred_at": f"2026-11-0{i}", "source": "codex", "event_type": "message.sent",
            "thread_id": "t", "actor_name": None, "content": content, "payload": {"big": "x" * 5000}}


def test_compact_windows_content_and_bounds_answer():
    rows = [_row(i, "a" * 3000 + " Sagora installée " + "b" * 3000) for i in range(1, 9)]
    out = events.compact(rows, "sagora", width=300, budget=1500)
    assert out["events"] and "payload" not in out["events"][0]
    assert "Sagora" in out["events"][0]["content"] and len(out["events"][0]["content"]) <= 302
    assert out["truncated"] == len(rows) - len(out["events"]) > 0 and "event_id" in out["hint"]


def test_order_is_validated():
    import pytest
    with pytest.raises(ValueError):
        events.get_events(order="sideways")
