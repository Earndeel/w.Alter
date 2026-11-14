"""Owner's pause of the extraction chain (2026-11-14): no model call, nothing claimed, health not alarmed."""
from walter_memory import consolidate, extract2, organic, views


def _paused(monkeypatch):
    cur = organic.settings()
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "extraction": {"mode": "paused"}})


def test_default_is_active_and_the_switch_reads_paused(monkeypatch):
    assert organic.extraction_paused() is False
    _paused(monkeypatch)
    assert organic.extraction_paused() is True


def test_paused_chain_claims_nothing_and_calls_no_model(monkeypatch):
    _paused(monkeypatch)
    monkeypatch.setattr(extract2, "claim", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claimed")))
    no_model = lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called"))   # noqa: E731
    r = extract2.tick(chat=no_model)
    assert r["paused"] is True and r["segments"] == 0
    assert views.run() == {"skipped": "extraction paused"}
    assert consolidate.reconsolidate("subject:x", chat=no_model) == {"skipped": "extraction paused"}
