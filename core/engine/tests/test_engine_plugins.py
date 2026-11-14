"""Lots E2–E4: the engine's plugins (intake, events, policy), its API door (core/interfaces/api) and the JS side of Walter's one execution policy
(Node, node:test) run with core's test suite."""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SUITES = [HERE / "plugins.test.mjs", HERE / "policy.test.mjs", HERE.parents[1] / "security" / "tests" / "policy.test.mjs",
          HERE.parents[1] / "interfaces" / "api" / "tests" / "api.test.mjs"]


@pytest.mark.parametrize("suite", SUITES, ids=[f"{p.parent.parent.name}/{p.name}" for p in SUITES])
def test_node_suite(suite):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", "--test", str(suite)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
