"""Owner's pause of the extraction chain (2026-11-14): no model call, nothing claimed, health not alarmed."""
from walter_memory import consolidate, extract2, organic, views


def _paused(monkeypatch, stages=None):
    cur = organic.settings()
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "extraction": {"mode": "paused"}, "stages": stages or {}})


def test_default_is_active_and_the_switch_reads_paused(monkeypatch):
    cur = organic.settings()
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "extraction": {"mode": "active"}, "stages": {}})
    assert organic.extraction_paused() is False
    _paused(monkeypatch)
    assert organic.extraction_paused() is True


def test_paused_chain_claims_nothing_and_calls_no_model(monkeypatch):
    _paused(monkeypatch)
    monkeypatch.setattr(extract2, "claim", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claimed")))
    no_model = lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called"))   # noqa: E731
    r = extract2.tick(chat=no_model)
    assert r["paused"] is True and r["segments"] == 0
    assert views.run() == {"skipped": "subjects paused"}
    assert consolidate.reconsolidate("subject:x", chat=no_model) == {"skipped": "reconsolidation paused"}


def test_each_stage_has_its_own_switch_and_an_absent_one_follows_extraction(monkeypatch):
    """A2 (2026-11-19): extraction, subjects, reconsolidation, episode summaries switch apart; an older config with
    only [extraction] mode keeps its meaning for all four."""
    _paused(monkeypatch, {"subjects": "active"})
    assert organic.stage("subjects") == {"mode": "active", "from": "stages"}
    assert organic.stage("reconsolidation") == {"mode": "paused", "from": "extraction"}
    assert organic.paused("extraction") and organic.extraction_paused()
    assert set(organic.stages()) == {"extraction", "catchup", "subjects", "reconsolidation", "episode_summaries"}
    cur = organic.settings()
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "extraction": {"mode": "active"},
                                                      "stages": {"extraction": "paused"}})
    assert organic.extraction_paused() and not organic.paused("subjects")
