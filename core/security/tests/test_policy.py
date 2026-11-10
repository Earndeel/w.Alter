"""The Python side of the one execution policy against the shared vectors (the JS side runs the same file)."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from walter_security import policy  # noqa: E402

ROOT = "/user/Test"
VECTORS = json.loads((HERE / "vectors.json").read_text())


def _sub(v):
    return json.loads(json.dumps(v).replace("@instance", ROOT))


@pytest.mark.parametrize("case", VECTORS, ids=[c["why"] for c in VECTORS])
def test_vector(case):
    p = policy.load(policy.POLICY, instance_root=ROOT)
    req = _sub(case["req"])
    out = policy.decide(p, tool=req["tool"], args=req.get("args"), interface=req.get("iface", "api"),
                        depth=req.get("depth", 0))
    assert out["decision"] == case["decision"], out
    if "rule" in case:
        assert out["rule"] == case["rule"]


def test_strictest_and_every_preset_complete():
    p = policy.load(policy.POLICY, instance_root=ROOT)
    assert policy.strictest("allow", "check", "ask") == "ask" and policy.strictest("deny", "allow") == "deny"
    classes = set(p["classes"]) | {"unknown"}
    for name, preset in p["presets"].items():
        assert classes <= set(preset), name
        assert set(preset.values()) <= set(policy.ORDER), name
    assert set(p["interfaces"].values()) <= set(p["presets"])
