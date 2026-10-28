"""walter matrix 'qualified' (P6): only a recent passing scenario qualifies a harness:capability pair."""
import datetime
import json

from walter_platform import harness_matrix


def test_recent_passes_qualify_old_ones_do_not(tmp_path, monkeypatch):
    now = datetime.datetime.now(datetime.timezone.utc)
    fmt = lambda d: (now - datetime.timedelta(days=d)).strftime("%Y%m%dT%H%M%SZ")
    f = tmp_path / "qualifications.json"
    f.write_text(json.dumps({"version": 1, "pairs": {
        "claude-code:browse": {"scenario": "e2e-minimal", "at": fmt(1), "run_id": "r1", "scope": "s"},
        "claude-code:memory": {"scenario": "cafe-glace", "at": fmt(30), "run_id": "r2", "scope": "s"},
        "claude-code:skills": {"scenario": "x", "at": "not-a-date"}}}))
    from walter_platform import instance
    monkeypatch.setattr(instance, "state", lambda *parts, **kw: str(f))
    q = harness_matrix._scenario_qualifications()
    assert set(q) == {"claude-code:browse"} and q["claude-code:browse"]["run_id"] == "r1"
