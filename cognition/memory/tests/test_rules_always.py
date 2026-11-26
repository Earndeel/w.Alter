"""[rules] always (organic.toml, payload plan lot 1, owner 2026-11-23): the rules injected with every message are the
owner's own instructions to Walter; rules learnt from his contacts' conversations or about one project come only when
the message is related to them. "all" (the default) is the behaviour before, so the rollback is the switch."""
from walter_memory import organic, working

CFG = {"relevance_only_channels": ["contact"], "relevance_only_subjects": ["project:"]}


def _with(monkeypatch, always):
    base = organic.DEFAULTS
    cfg = {**base, "rules": {**base["rules"], **CFG, "always": always}}
    monkeypatch.setattr(organic, "settings", lambda: cfg)


def test_all_keeps_every_rule_by_recency(monkeypatch):
    _with(monkeypatch, "all")
    assert working._always_shown({"channel": "contact", "subject": "owner"})
    assert working._always_shown({"channel": None, "subject": "project:sagora"})


def test_instructions_keep_only_what_the_owner_told_walter_outside_a_project(monkeypatch):
    _with(monkeypatch, "instructions")
    assert working._always_shown({"channel": None, "subject": "owner"})
    assert working._always_shown({"channel": None, "subject": "walter"})
    assert working._always_shown({"channel": None, "subject": None})
    assert not working._always_shown({"channel": "contact", "subject": "owner"})        # said to a contact
    assert not working._always_shown({"channel": None, "subject": "project:sagora"})    # about one project


def test_the_default_is_the_behaviour_before():
    assert organic.DEFAULTS["rules"]["always"] == "all"


def test_a_repeated_rule_is_shown_with_its_newest_date():
    """23/11: owner_rules hands densify its rows newest first, densify keeps the last of a set of near-duplicates —
    the oldest wording and date were the ones shown. Now the newest copy is kept, in its place."""
    import json
    import uuid
    from datetime import datetime, timedelta, timezone
    from walter_memory import events, extract2, generations
    now = datetime.now(timezone.utc)
    extract2.set_v1_start(now - timedelta(days=10))
    generations.rollback(confirm=True)
    tag = uuid.uuid4().hex[:6]
    text = f"Les comptes rendus du chantier {tag} sont envoyés le lundi"
    for days in (6, 0):
        thread = f"rr-{uuid.uuid4().hex[:8]}"
        events.record_events([{"event_type": "message.sent", "source": "codex", "source_account": "pytest",
                               "source_id": uuid.uuid4().hex, "thread_id": thread, "content": text,
                               "occurred_at": now - timedelta(days=days, hours=1), "privacy_class": "cloud_allowed"}])
        item = {"kind": "preference", "text": text, "msgs": [1], "scope": "durable", "quote": text}
        extract2.process_thread("codex", thread, force=True, chat=lambda messages, **kw: {
            "content": json.dumps({"summary": "", "items": [item]}), "cost_usd": 0, "model": "scripted",
            "usage": {"prompt_tokens": 10}})
    r = working.owner_rules(f"quand part le compte rendu du chantier {tag} ?", budget=2000)
    line = next(x for x in r["text"].splitlines() if tag in x)
    assert f"({now:%d/%m/%Y})" in line, line
