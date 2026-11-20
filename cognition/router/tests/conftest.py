"""Tests never write the active instance's files: every instance-owned file goes to the test's temporary folder."""
import sys
from pathlib import Path

import pytest

from walter_router import instance

# The suite also covers the gateway (llm/gateway.py: FastAPI, litellm), whose packages live in its own environment
# (llm/venv): appended after this venv's own, so the router's versions always win (2026-11-20: without them six
# gateway test files failed to collect and the guardian chased them as failures for a week).
for _sp in sorted((Path(__file__).resolve().parents[1] / "llm" / "venv").glob("lib/python3*/site-packages")):
    if str(_sp) not in sys.path:
        sys.path.append(str(_sp))


@pytest.fixture(autouse=True)
def _instance_files_stay_out_of_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(instance, "own_file", lambda name: tmp_path / "instance" / name)
    monkeypatch.setattr(instance, "state_file", lambda name: tmp_path / "instance-state" / name)


@pytest.fixture(autouse=True)
def _no_live_engine(monkeypatch):
    """The instance binds walter_run to the live engine (2026-11-10): a test never reaches it unless it sets its own
    test engine (test_engine_run)."""
    monkeypatch.setenv("WALTER_RUN_ENGINE", "legacy")
