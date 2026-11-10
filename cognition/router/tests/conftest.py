"""Tests never write the active instance's files: every instance-owned file goes to the test's temporary folder."""
import pytest

from walter_router import instance


@pytest.fixture(autouse=True)
def _instance_files_stay_out_of_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(instance, "own_file", lambda name: tmp_path / "instance" / name)
    monkeypatch.setattr(instance, "state_file", lambda name: tmp_path / "instance-state" / name)


@pytest.fixture(autouse=True)
def _no_live_engine(monkeypatch):
    """The instance binds walter_run to the live engine (2026-11-10): a test never reaches it unless it sets its own
    test engine (test_engine_run)."""
    monkeypatch.setenv("WALTER_RUN_ENGINE", "legacy")
