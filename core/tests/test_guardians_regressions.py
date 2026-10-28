"""Supervisor regressions: real fixture subprocesses and a fake delivery transport only."""
import json
import subprocess
import sys
from pathlib import Path

from test_guardians import G


def decl(tmp_path, payload, rc=0):
    script = tmp_path / "check.py"
    script.write_text(f"import sys\nprint({json.dumps(payload)!r})\nsys.exit({rc})\n")
    return {"version": 1, "module": "a", "check": [sys.executable, str(script)]}


def incident(severity="high"):
    return {"version": 1, "module": "a", "key": "down", "kind": "service_down", "severity": severity, "summary": "indisponible"}


def test_nonzero_empty_json_cannot_be_healthy(tmp_path):
    _, items, meta = G.run_check(decl(tmp_path, [], 7))
    assert meta["ok"] is False
    assert items[0]["key"] == "guardian:unreachable"


def test_invalid_or_foreign_incident_cannot_be_silently_discarded(tmp_path):
    for bad in ({"version": 1, "module": "a", "key": "x", "severity": "high"},
                {**incident(), "module": "foreign"}, {**incident(), "evidence": "invalid"}):
        _, items, meta = G.run_check(decl(tmp_path, [bad]))
        assert meta["ok"] is False and items[0]["key"] == "guardian:unreachable"


def test_failed_delivery_is_retained_and_retried_with_backoff(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    monkeypatch.setattr(G, "declarations", lambda: [decl(tmp_path, [incident()])])
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda msg: sent.append(msg) or len(sent) > 1)
    clock = [1000000.0]
    monkeypatch.setattr(G.time, "time", lambda: clock[0])
    G.check()
    G.check()
    assert len(sent) == 1
    clock[0] += 901
    G.check()
    assert len(sent) == 2
    G.check()
    assert len(sent) == 2


def test_severity_escalation_alerts_again_and_no_notify_preserves_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    severity = ["warning"]
    monkeypatch.setattr(G, "declarations", lambda: [decl(tmp_path, [incident(severity[0])])])
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda msg: sent.append(msg) or True)
    G.check()
    severity[0] = "high"
    G.check(notify=False)
    assert sent == []
    G.check()
    assert len(sent) == 1
    severity[0] = "critical"
    G.check()
    assert len(sent) == 2


def test_retry_is_bounded_and_failed_watchdog_cannot_close_prior_incident(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    failed = [False]
    monkeypatch.setattr(G, "declarations", lambda: [decl(tmp_path, [] if failed[0] else [incident()], 1 if failed[0] else 0)])
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda msg: sent.append(msg) or False)
    clock = [1000000.0]
    monkeypatch.setattr(G.time, "time", lambda: clock[0])
    for _ in range(12):
        G.check()
        clock[0] += 30000
    assert len(sent) == 5
    failed[0] = True
    report = G.check(notify=False)
    assert "a:down" not in report["closed"]


def test_timeout_and_duplicate_incidents_fail_closed(tmp_path):
    d = decl(tmp_path, [])
    d["check"] = [sys.executable, "-c", "import time; time.sleep(1)"]
    d["timeout_seconds"] = 0.01
    _, items, meta = G.run_check(d)
    assert not meta["ok"] and items[0]["severity"] == "high"
    _, _, meta = G.run_check(decl(tmp_path, [incident(), incident()]))
    assert not meta["ok"]


def test_batched_notifications_acknowledge_only_sent_items(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    payload = [{**incident(), "key": str(i)} for i in range(13)]
    monkeypatch.setattr(G, "declarations", lambda: [decl(tmp_path, payload)])
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda msg: sent.append(msg) or True)
    assert G.check()["pending_notifications"] == 3
    assert len(G.status()["pending_delivery"]) == 3
    assert G.check()["pending_notifications"] == 0
    assert len(sent) == 2


def test_discovery_failure_is_explicit_not_an_empty_healthy_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    monkeypatch.setattr(G, "sh", lambda *a, **kw: subprocess.CompletedProcess(a, 7, "{}", "private output"))
    report = G.check(notify=False)
    assert report["opened"] == ["core:guardian:unreachable"]
    assert report["modules"]["core"]["ok"] is False
    assert "private output" not in (tmp_path / "state/guardians/state.json").read_text()


def test_malformed_existing_declaration_is_an_incident(tmp_path, monkeypatch):
    root = tmp_path / "module"
    (root / "contracts").mkdir(parents=True)
    (root / "contracts/maintenance.json").write_text('not valid JSON')
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    monkeypatch.setattr(G, "sh", lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps({"modules": [{"id": "a", "root": str(root)}]}), ""))
    report = G.check(notify=False)
    assert report["opened"] == ["a:guardian:unreachable"]
