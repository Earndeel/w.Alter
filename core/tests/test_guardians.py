"""walter-guardians (P5): declared watchdogs, incident life cycle, Telegram only for new high/critical incidents."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "bin" / "walter-guardians"
loader = importlib.machinery.SourceFileLoader("walter_guardians", str(SRC))
spec = importlib.util.spec_from_loader("walter_guardians", loader)
G = importlib.util.module_from_spec(spec); loader.exec_module(G)


def _decl(tmp_path, name, payload):
    script = tmp_path / f"{name}.py"
    script.write_text(f"import json,sys; print({payload!r})")
    return {"version": 1, "module": name, "check": ["python3", str(script)], "timeout_seconds": 20}


def test_life_cycle_and_sparse_notification(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    sent = []
    monkeypatch.setattr(G, "_telegram", lambda text: sent.append(text) or True)
    high = json.dumps([{"version": 1, "module": "a", "key": "k1", "kind": "x", "severity": "high", "summary": "panne"},
                       {"version": 1, "module": "a", "key": "k2", "kind": "x", "severity": "info", "summary": "note"}])
    monkeypatch.setattr(G, "declarations", lambda: [_decl(tmp_path, "a", high), _decl(tmp_path, "b", "pas du json")])
    r1 = G.check(notify=True)
    assert set(r1["opened"]) == {"a:k1", "a:k2", "b:guardian:unreachable"}
    assert len(sent) == 1 and "panne" in sent[0] and "note" not in sent[0]           # only new high/critical
    r2 = G.check(notify=True)
    assert r2["opened"] == [] and len(sent) == 1                                     # same incidents: no repeat
    monkeypatch.setattr(G, "declarations", lambda: [_decl(tmp_path, "a", "[]"), _decl(tmp_path, "b", "[]")])
    r3 = G.check(notify=True)
    assert set(r3["closed"]) == {"a:k1", "a:k2", "b:guardian:unreachable"} and r3["open"] == 0
    events = [json.loads(l)["event"] for l in (tmp_path / "inst/state/guardians/incidents.jsonl").read_text().splitlines()]
    assert events.count("opened") == 3 and events.count("closed") == 3


def test_malformed_incidents_fail_the_watchdog(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    monkeypatch.setattr(G, "_telegram", lambda text: True)
    bad = json.dumps([{"module": "c", "key": "k", "severity": "high"}, {"version": 1, "module": "c", "key": "ok",
                                                                         "kind": "x", "severity": "loud", "summary": "?"}])
    monkeypatch.setattr(G, "declarations", lambda: [_decl(tmp_path, "c", bad)])
    assert G.check(notify=False)["opened"] == ["c:guardian:unreachable"]
