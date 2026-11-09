"""walter-backup core: configuration merge, freshness, checkpoints that leave HEAD and the index alone, incidents."""
import json
import subprocess
from pathlib import Path

from walter_backup import core


def test_instance_overrides_module_defaults(tmp_path, monkeypatch):
    (tmp_path / "config" / "backup").mkdir(parents=True)
    (tmp_path / "config" / "backup" / "backup.toml").write_text('[git]\ndirty_warn_hours = 5\n[kinds.pg]\nunit = "u"\n')
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    cfg = core.config()
    assert cfg["git"]["dirty_warn_hours"] == 5 and cfg["kinds"]["pg"]["unit"] == "u"
    assert cfg["restore"]["min_free_gib_drill"] == 16                      # default kept


def test_newest_file_of_a_pattern(tmp_path):
    (tmp_path / "a-1.dump").write_text("x"); (tmp_path / "b.txt").write_text("y")
    n = core.newest(str(tmp_path), "a-*.dump")
    assert n["file"] == "a-1.dump" and n["count"] == 1 and n["age_h"] is not None
    assert core.newest(str(tmp_path / "missing"), "*") is None


def test_git_checkpoint_keeps_head_index_and_working_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "inst"))
    repo = tmp_path / "repo"; repo.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout
    g("init", "-q"); (repo / "f.txt").write_text("v1\n"); g("add", "f.txt")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c1")
    head = g("rev-parse", "HEAD").strip()
    (repo / "f.txt").write_text("v2 uncommitted\n")
    rec = core.checkpoint("git", str(repo), note="test")
    assert g("rev-parse", "HEAD").strip() == head and (repo / "f.txt").read_text() == "v2 uncommitted\n"
    assert g("diff", "--cached", "--name-only") == ""                     # index untouched
    assert "v2 uncommitted" in g("show", f"{rec['commit']}:f.txt")         # the ref holds the uncommitted state
    assert rec["ref"].startswith("refs/walter-backup/checkpoints/")
    assert json.loads((tmp_path / "inst" / "state" / "backup" / "checkpoints.jsonl").read_text().splitlines()[-1])["level"] == "git"


def test_check_turns_status_into_incident_v1(monkeypatch):
    monkeypatch.setattr(core, "status", lambda: {
        "conformity": {"ok": False},
        "backup_health": {"offsite": {"ok": False, "age_h": 50, "max_age_hours": 26}, "pg": {"ok": True}},
        "restorability": {"offsite_restore_test": {"ok": True}, "disk": {"drill_possible_now": False, "free_gib": 10,
                                                                         "needed_for_drill_gib": 16}}})
    monkeypatch.setattr(core, "git_inventory", lambda: [])
    monkeypatch.setattr(core, "engine_kernel", lambda: None)
    inc = {i["key"]: i for i in core.check()}
    assert set(inc) == {"conformity", "backup:offsite", "restore:disk"}
    assert inc["backup:offsite"]["severity"] == "critical" and inc["backup:offsite"]["version"] == 1
    assert all({"module", "kind", "summary", "evidence", "suggested_level"} <= set(i) for i in inc.values())


def test_engine_kernel_drift_is_an_owner_incident(monkeypatch):
    monkeypatch.setattr(core, "status", lambda: {"conformity": {"ok": True}, "backup_health": {},
                                                 "restorability": {"disk": {"drill_possible_now": True}}})
    monkeypatch.setattr(core, "git_inventory", lambda: [])
    monkeypatch.setattr(core, "engine_kernel", lambda: {"ok": True})
    assert core.check() == []
    monkeypatch.setattr(core, "engine_kernel", lambda: {"ok": False, "changed": ["@deepseek-ai/dsh"]})
    inc = {i["key"]: i for i in core.check()}
    assert inc["engine:kernel"]["kind"] == "engine_kernel_drift" and inc["engine:kernel"]["suggested_level"] == "G3"


def test_offsite_reads_the_remote_and_flags_a_missing_off_vm_key(monkeypatch):
    import subprocess as sp
    def fake_sh(*cmd, timeout=60, input=None):
        if cmd[0] == "rclone":
            kind = cmd[2].rstrip("/").split("/")[-1]
            files = [] if kind == "statedb" else [{"Name": f"{kind}-1.age", "ModTime": "2000-01-01T00:00:00Z", "Size": 10},
                                                   {"Name": f"{kind}-2.age", "ModTime": datetime_now(), "Size": 10}]
            return sp.CompletedProcess(cmd, 0, json.dumps(files), "")
        if cmd[0] == "walter-secret":
            return sp.CompletedProcess(cmd, 0, json.dumps([{"name": "something else"}]), "")
        return sp.CompletedProcess(cmd, 1, "", "")
    monkeypatch.setattr(core, "sh", fake_sh)
    out = core.offsite({"offsite": {"remote": "r:", "kinds": ["pg", "statedb"], "max_age_hours": 26,
                                    "recovery_key_item": "W.Alter recovery key (age)"}})
    assert out["kinds"]["pg"]["ok"] and out["kinds"]["pg"]["files"] == 2 and out["kinds"]["pg"]["newest"] == "pg-2.age"
    assert out["kinds"]["statedb"] == {"ok": False, "files": 0} and out["recovery_key_off_vm"] is False


def test_push_offsite_encrypts_then_copies_and_removes_the_encrypted_copy(tmp_path, monkeypatch):
    import subprocess as sp
    calls = []
    def fake_sh(*cmd, timeout=60, input=None):
        calls.append(cmd)
        if cmd[0] == "age":
            Path(cmd[cmd.index("-o") + 1]).write_text("enc")
        return sp.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(core, "sh", fake_sh)
    f = tmp_path / "pg-x.dump"; f.write_text("data")
    res = core.push_offsite(f, {"offsite": {"remote": "r:", "recipient": "/k.pub"}})
    assert res == {"ok": True, "remote": "r:/checkpoints/pg-x.dump.age"}
    assert calls[0][:3] == ("age", "-R", "/k.pub") and calls[1][0] == "rclone"
    assert f.exists() and not (tmp_path / "pg-x.dump.age").exists()


def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_restic_status_reads_last_run_and_password_copy(tmp_path, monkeypatch):
    import json, subprocess
    (tmp_path / "restic-last.json").write_text(json.dumps({"at": "x", "ok": True, "snapshots": [{"tag": "pg"}],
                                                           "repository_bytes": 2**30}))
    monkeypatch.setattr(core, "sh", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps([{"name": "P"}]), ""))
    out = core.restic({"restic": {"repository": "r", "state_dir": str(tmp_path), "password_item": "P"}})
    assert out["last"]["ok"] is True and out["last"]["repository_gib"] == 1.0 and out["password_off_vm"] is True
    assert core.restic({}) == {"configured": False}
