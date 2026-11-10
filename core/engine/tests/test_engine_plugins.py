"""Lot E2: the engine's intake and events plugins (Node, node:test) run with core's test suite."""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def test_intake_and_events_plugins():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", "--test", str(HERE / "plugins.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
