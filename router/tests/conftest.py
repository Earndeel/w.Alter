"""Tests never write the active instance's files: every instance-owned file goes to the test's temporary folder."""
import pytest

from walter_router import instance


@pytest.fixture(autouse=True)
def _instance_files_stay_out_of_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(instance, "own_file", lambda name: tmp_path / "instance" / name)
