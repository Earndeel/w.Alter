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
