"""Stable block (owner 2026-11-26): the pack leaves the universal consignes out only when the host says it carries them
in its instructions for this turn (`socle_rules` in the preflight request)."""
from walter_context import retrieval


def test_session_state_passes_the_hosts_word_to_memory(monkeypatch):
    from walter_memory import context
    seen = []
    monkeypatch.setattr(context, "get_context", lambda q, **kw: seen.append(kw.get("exclude_universal")) or {"text": ""})
    retrieval.session_state(None, "bonjour", None)
    retrieval.session_state(None, "bonjour", None, socle_rules=True)
    assert seen == [False, True]
