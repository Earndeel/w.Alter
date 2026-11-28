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


@pytest.mark.parametrize("iface,expected", [("api", "allow"), ("test", "allow"), ("telegram", "allow"),
                                            ("web", "allow"), ("command", "deny")])
def test_creating_a_task_is_a_local_record_not_a_sensitive_action(iface, expected):
    """E2E 20/11 (owner: « ne classe pas automatiquement toute écriture locale comme une action externe sensible »):
    creating a task (its reminder goes to the owner only, a test run's stays in its channel) is allowed on every door
    but the narrow command one, while changing an existing task from an unattended door still asks, and sending a
    message stays outgoing."""
    p = policy.load(policy.POLICY, instance_root=ROOT)
    out = policy.decide(p, tool="mcp__walter__task_create", args={"goal": "relancer"}, interface=iface)
    assert out["class"] == "record" and out["decision"] == expected, out
    assert policy.decide(p, tool="mcp__walter__task_update", args={"task_id": "t"}, interface="api")["decision"] == "ask"
    assert policy.classify(p, "mcp__walter__beeper_send_message") == "outgoing"


def test_module_guardians_work_like_the_owner_in_a_dev_session_but_send_nothing():
    """2026-11-20 (Monsieur): a module guardian fixes what broke the way he would from Claude Code, without him."""
    p = policy.load(policy.POLICY, instance_root=ROOT)
    assert p["machine_interfaces"]["guardian-"] == "maintenance"
    shell = policy.decide(p, tool="bash", args={"command": "pytest -q"}, interface="maintenance")
    write = policy.decide(p, tool="write", args={"file_path": "/walter/x.py"}, interface="maintenance")
    assert shell["decision"] == write["decision"] == "allow"
    out = policy.decide(p, tool="mcp__walter__beeper_send_message", args={}, interface="maintenance")
    assert out["decision"] == "check"           # an unattended run has nobody to approve it: never sent
    secret = policy.decide(p, tool="bash", args={"command": f"cat {ROOT}/bootstrap/engine/api.token"},
                           interface="maintenance")
    assert secret["decision"] == "deny"
