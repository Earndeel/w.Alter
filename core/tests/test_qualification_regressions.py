"""A recent date alone never establishes current-source qualification."""
import datetime
import json
from walter_platform import harness_matrix
from walter_platform import instance


def recent():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_unattested_legacy_pass_is_historical_only(tmp_path, monkeypatch):
    path = tmp_path / "qualifications.json"
    path.write_text(json.dumps({"version": 1, "pairs": {"claude-code:browse": {"scenario": "e2e-minimal", "at": recent(), "run_id": "old"}}}))
    monkeypatch.setattr(instance, "state", lambda *a: path)
    assert harness_matrix._scenario_qualifications() == {}


def test_unknown_attestation_version_is_not_qualified(tmp_path, monkeypatch):
    path = tmp_path / "qualifications.json"
    path.write_text(json.dumps({"version": 2, "pairs": {"claude-code:browse": {"scenario": "e2e-minimal", "at": recent(), "run_id": "old", "attestation": {"version": 999}}}}))
    monkeypatch.setattr(instance, "state", lambda *a: path)
    assert harness_matrix._scenario_qualifications() == {}


def test_dirty_source_and_scenario_changes_invalidate_attested_evidence(tmp_path, monkeypatch):
    import subprocess
    from walter_platform import qualification as Q
    from test_scenario_regressions import S
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    code = root / "entry.py"
    code.write_text("value = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "entry.py"], check=True)
    cfg = tmp_path / "harness.json"
    cfg.write_text("{}")
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    scenario = scenario_dir / "fixture.yaml"
    scenario.write_text('name: fixture\nqualifies:\n  - {harness: claude-code, capability: browse}\n')
    modules = [{"id": m, "root": str(root), "requires": [], "contract": {"version": "1.0.0"}}
               for m in ("core", "memory", "logs", "router", "llm", "runtime", "browse")]
    monkeypatch.setattr(Q, "CORE", root)
    monkeypatch.setattr(Q.registry, "load", lambda: {"modules": modules})
    monkeypatch.setattr(Q.harness, "config_path", lambda host: cfg)
    import yaml
    sc = yaml.safe_load(scenario.read_text())
    proof = {"scenario": "fixture", "run_id": "fixture", "at": recent(), "ok": True,
             "attestation": Q.attest(sc, scenario)}
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "instance"))
    S.qualify(sc, proof)
    assert Q.current(proof, core=tmp_path)
    old_source = Q.source_snapshot(root)
    code.write_text("value = 2\n")
    assert Q.source_snapshot(root) != old_source
    assert not Q.current(proof, core=tmp_path)
    code.write_text("value = 1\n")
    assert Q.current(proof, core=tmp_path)
    scenario.write_text(scenario.read_text() + "# acceptance changed\n")
    assert not Q.current(proof, core=tmp_path)
    scenario.write_text('name: fixture\nqualifies:\n  - {harness: claude-code, capability: browse}\n')
    assert Q.current(proof, core=tmp_path)
    cfg.write_text('{"changed": true}')
    assert not Q.current(proof, core=tmp_path)
    cfg.write_text('{}')
    modules[0]["contract"]["version"] = "2.0.0"
    assert not Q.current(proof, core=tmp_path)


def test_new_source_files_invalidate_without_commit_and_ignored_state_does_not(tmp_path):
    import subprocess
    from walter_platform import qualification as Q
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "entry.py").write_text("pass\n")
    original = Q.source_snapshot(tmp_path)
    (tmp_path / "addition.py").write_text("pass\n")
    assert Q.source_snapshot(tmp_path) != original
    (tmp_path / "addition.py").unlink()
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.json").write_text('{"updated": true}')
    assert Q.source_snapshot(tmp_path) == original
