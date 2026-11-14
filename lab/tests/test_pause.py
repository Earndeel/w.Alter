"""Lab paused until production (owner decision 2026-10-29): no run without the owner's explicit request."""
import pytest

from walter_lab import core

EXP = {"name": "x", "hypothesis": "h", "scenario": "s", "repeats": 1, "variants": {"base": {}, "new": {}},
       "metrics": ["ok"], "decision": {"prefer": "new", "if": ["ok_rate >= baseline"]}}


def _instance(tmp_path, monkeypatch, text=None):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    if text is not None:
        (tmp_path / "config" / "lab").mkdir(parents=True)
        (tmp_path / "config" / "lab" / "lab.toml").write_text(text)
    monkeypatch.setattr(core, "load", lambda name: EXP)
    calls = []
    monkeypatch.setattr(core, "run_scenario", lambda s, env, v, timeout=1800: calls.append(v) or {"ok": True, "metrics": {}})
    return calls


def test_paused_refuses_without_owner_request(tmp_path, monkeypatch):
    calls = _instance(tmp_path, monkeypatch, 'mode = "paused"\n')
    with pytest.raises(core.LabPaused):
        core.run("x")
    with pytest.raises(core.LabPaused):
        core.run("x", requested_by="owner", reason="  ")
    assert calls == []


def test_owner_request_runs_and_is_recorded(tmp_path, monkeypatch):
    calls = _instance(tmp_path, monkeypatch, 'mode = "paused"\n')
    rep = core.run("x", requested_by="owner", reason="owner: compare both modes")
    assert calls == ["base", "new"]
    assert rep["request"] == {"mode": "paused", "requested_by": "owner", "reason": "owner: compare both modes"}


def test_module_default_is_paused_and_unknown_mode_is_paused(tmp_path, monkeypatch):
    _instance(tmp_path, monkeypatch)
    assert core.mode()["mode"] == "paused"                         # module config/lab.toml
    (tmp_path / "config" / "lab").mkdir(parents=True)
    (tmp_path / "config" / "lab" / "lab.toml").write_text('mode = "sometimes"\n')
    assert core.mode()["mode"] == "paused"


def test_active_runs_without_request(tmp_path, monkeypatch):
    calls = _instance(tmp_path, monkeypatch, 'mode = "active"\n')
    assert core.run("x")["request"]["mode"] == "active" and calls
