"""walter-lab: summaries over interleaved runs and the decision rule written before the runs (no scenario run here)."""
from walter_lab import core

EXP = {"name": "x", "hypothesis": "h", "scenario": "s", "variants": {"base": {}, "new": {}},
       "metrics": ["ok", "model_calls"], "decision": {"prefer": "new", "if": ["ok_rate >= baseline", "median model_calls <= baseline"]}}


def r(variant, ok, calls):
    return {"variant": variant, "ok": ok, "metrics": {"model_calls": calls}}


def test_summary_counts_failures_and_ignores_their_metrics():
    s = core.summarise([r("base", True, 6), r("base", False, 40), r("new", True, 4), r("new", True, 5)], EXP["metrics"])
    assert s["base"] == {"n": 2, "ok_rate": 0.5, "median model_calls": 23}
    assert s["new"] == {"n": 2, "ok_rate": 1.0, "median model_calls": 4.5}


def test_decision_proposes_the_candidate_only_when_every_condition_holds():
    good = core.decide(EXP, {"base": {"ok_rate": 0.5, "median model_calls": 6}, "new": {"ok_rate": 1.0, "median model_calls": 4.5}})
    assert good["proposal"] == "adopter new" and good["applied"] is False
    bad = core.decide(EXP, {"base": {"ok_rate": 1.0, "median model_calls": 4}, "new": {"ok_rate": 1.0, "median model_calls": 7}})
    assert bad["proposal"].startswith("ne rien changer") and not bad["checks"][1]["holds"]


def test_missing_measures_never_make_a_condition_true():
    d = core.decide(EXP, {"base": {"ok_rate": 1.0}, "new": {"ok_rate": 1.0}})
    assert d["proposal"].startswith("ne rien changer")


def test_sandbox_command_is_isolated(monkeypatch, tmp_path):
    """The docker invocation itself: no network, read-only, no capability, unprivileged, only the work copy mounted."""
    from walter_lab import sandbox
    seen = {}
    import subprocess as sp
    monkeypatch.setattr(sandbox.subprocess, "run", lambda argv, **kw: seen.setdefault("argv", argv) and sp.CompletedProcess(argv, 0, "", ""))
    sandbox.run(None, ["true"], timeout=5)
    a = seen["argv"]
    assert a[a.index("--network") + 1] == "none" and "--read-only" in a and a[a.index("--cap-drop") + 1] == "ALL"
    assert a[a.index("--user") + 1] == "65534:65534" and "no-new-privileges" in a
    mounts = [a[i + 1] for i, x in enumerate(a) if x == "-v"]
    assert len(mounts) == 1 and mounts[0].endswith(":/work") and "walter-lab-sandbox-" in mounts[0]
