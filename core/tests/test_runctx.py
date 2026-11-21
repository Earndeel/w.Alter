"""hooks/runctx.py — how a tool process finds the current Walter run (adapter detail, 2026-10-27)."""
import importlib.util
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("runctx", Path(__file__).resolve().parent.parent / "hooks" / "runctx.py")
runctx = importlib.util.module_from_spec(spec); spec.loader.exec_module(runctx)


def test_record_then_current_by_parent_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path)); monkeypatch.delenv("WALTER_RUN_ID", raising=False)
    runctx.record(4242, "01a1-run", "claude_code/vm/s", "claude_code")
    assert runctx.current(4242)["run_id"] == "01a1-run"
    assert runctx.env(4242) == {"WALTER_RUN_ID": "01a1-run", "WALTER_SESSION_ID": "claude_code/vm/s"}
    assert oct((tmp_path / "state/runs/current/4242.json").stat().st_mode & 0o777) == "0o600"


def test_explicit_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    runctx.record(4243, "recorded", "s", "claude_code")
    monkeypatch.setenv("WALTER_RUN_ID", "explicit"); monkeypatch.setenv("WALTER_TASK_ID", "t1")
    assert runctx.current(4243)["run_id"] == "explicit" and runctx.env(4243)["WALTER_TASK_ID"] == "t1"


def test_unknown_or_stale_record_gives_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path)); monkeypatch.delenv("WALTER_RUN_ID", raising=False)
    assert runctx.current(999999) is None and runctx.env(999999) == {}


def test_harness_pid_skips_shells_and_honours_the_scenario_override(monkeypatch):
    monkeypatch.setenv("WALTER_HARNESS_PID", "777")
    assert runctx.harness_pid() == 777
    monkeypatch.delenv("WALTER_HARNESS_PID")
    pid = runctx.harness_pid()
    comm = Path(f"/proc/{pid}/comm").read_text().strip()
    assert comm not in runctx.SKIP and not comm.startswith("python")
