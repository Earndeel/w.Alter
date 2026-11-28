"""walter-ops (2026-10-29): walter-backup's commands keep the same outputs under `walter-ops backup`; incidents now
carry the module id `ops`; the installer answers `planned` until it is built."""
import json

from walter_backup import cli as backup_cli
from walter_backup import core
from walter_ops import cli as ops_cli


def _out(capsys, fn, args):
    rc = fn(args)
    return rc, capsys.readouterr().out


def test_backup_commands_have_identical_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    (tmp_path / "state" / "backup").mkdir(parents=True)
    (tmp_path / "state" / "backup" / "checkpoints.jsonl").write_text(json.dumps({"level": "git", "ref": "r"}) + "\n")
    assert _out(capsys, backup_cli.main, ["checkpoints"]) == _out(capsys, ops_cli.main, ["backup", "checkpoints"])


def test_git_and_check_are_top_level_aliases(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(backup_cli, "main", lambda args: seen.append(args) or 0)
    assert ops_cli.main(["git"]) == 0 and ops_cli.main(["check"]) == 0
    assert ops_cli.main(["recovery", "drill"]) == 0
    assert seen == [["git"], ["check"], ["run", "restore_drill"]]


def test_incidents_carry_the_ops_module_id():
    assert core.incident("k", "kind", "info", "s", {})["module"] == "ops"


def test_installer_is_planned_not_pretended(capsys):
    assert ops_cli.main(["install", "clean"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "planned"


def test_unknown_and_bad_usage_fail(capsys):
    assert ops_cli.main(["recovery", "everything"]) == 2
    assert ops_cli.main(["nope"]) == 2


def test_job_parameters_come_from_configuration(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    (tmp_path / "config" / "backup").mkdir(parents=True)
    conf = tmp_path / "config" / "backup" / "backup.toml"
    conf.write_text('[kinds.pg]\ndir = "/b/pg"\npattern = "db-*.dump"\n[pg]\ncontainer = "c"\ndatabase = "d"\nuser = "u"\n'
                    '[offsite]\nremote = "r:x"\nrecipient = "/k.pub"\nkinds = ["pg", "config"]\nvault_export_dir = "/v"\n'
                    '[kinds.statedb]\ndir = "/b/s"\npattern = "s-*.zst"\nsource = "/s.db"\n')
    env = core.job_env("pg")
    assert (env["WALTER_BACKUP_PREFIX"], env["WALTER_BACKUP_SUFFIX"]) == ("db-", ".dump")
    assert env["WALTER_BACKUP_KEEP_DAILY"] == "7" and env["WALTER_PG_CONTAINER"] == "c"   # module default retention
    assert core.job_env("offsite")["WALTER_OFFSITE_KINDS"] == "pg config"
    assert "WALTER_OFFSITE_PROJECTS" not in core.job_env("offsite")   # optional: absent unless the instance sets it
    conf.write_text(conf.read_text().replace('vault_export_dir = "/v"\n', 'vault_export_dir = "/v"\nprojects = ["/p", "/q"]\n'))
    assert core.job_env("offsite")["WALTER_OFFSITE_PROJECTS"] == "/p /q"
    conf.write_text('[kinds.pg]\npattern = "db-*.dump"\n')
    with pytest.raises(ValueError, match="kinds.pg.dir"):
        core.job_env("pg")                                        # never a guessed location
    with pytest.raises(ValueError):
        core.job_env("unknown")


def test_scripts_carry_no_location_of_their_own():
    from pathlib import Path
    for script in (Path(__file__).resolve().parents[1] / "backup" / "scripts").iterdir():
        text = script.read_text()
        assert "walter-ops backup env" in text and str(Path.home()) + "/" not in text and "/home/" not in text, script.name


def test_a_restore_proven_seconds_ago_counts(monkeypatch):
    monkeypatch.setattr(core, "unit_last", lambda unit: {"unit": unit, "result": "success", "last_success_age_h": 0.0})
    cfg = {"kinds": {"restore_test": {"unit": "u", "max_age_hours": 840}}}
    assert core.restorability(cfg)["offsite_restore_test"]["ok"] is True
    monkeypatch.setattr(core, "unit_last", lambda unit: {"unit": unit, "result": "success", "last_success_age_h": None})
    assert core.restorability(cfg)["offsite_restore_test"]["ok"] is False
