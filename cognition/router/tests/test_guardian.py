"""Guardian (2026-10-26): detection rules, the agent's verdict, the gates and the landing rules of a patch."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from walter_router import paths
from walter_router.guardian import checks, repair, run


def _repo(root, files: dict[str, str]):
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True)
    return root


@pytest.mark.parametrize("detail,side", [
    ("HTTP 200 (réponse incomplète)", "external"),
    ("HTTP 503: upstream", "external"),
    ("HTTP 429: slow down", "external"),
    ("TimeoutError: timed out", "external"),
    ("HTTP 404: model not found", "ours"),
    ("HTTP 400: unknown parameter", "ours"),
    ("HTTP 401: invalid key", "account"),
    ("crédit épuisé : 0.10 $ restant", "account"),
])
def test_provider_failure_side(detail, side):
    assert checks.provider_side(detail) == side


def _inc(status, opened_h=1.0, **verdict):
    return {"incident_id": 1, "kind": "provider_down", "subject": "kie", "status": status,
            "opened_at": datetime.now(timezone.utc) - timedelta(hours=opened_h), "detail": {"probe": "HTTP 503"},
            "verdict": verdict}


def test_owner_hears_only_what_is_worth_it():
    assert run._message(_inc("external", 3)) is None
    assert "panne extérieure" in run._message(_inc("external", 50))
    assert run._message(_inc("open")) is None
    assert "réparé tout seul" in run._message(_inc("fixed", summary_fr="La page a changé.", apply={"applied": True}))
    assert run._message(_inc("fixed", apply={"applied": False})) is None
    msg = run._message(_inc("needs_owner", summary_fr="Le test attend Grok.", question_fr="Garder HeyGen ?"))
    assert "besoin de vous" in msg and "Garder HeyGen ?" in msg


def test_failing_test_waits_for_work_in_progress():
    now = datetime.now(timezone.utc)
    fresh = {"kind": "test_failure", "attempts": 0, "last_attempt_at": None, "opened_at": now - timedelta(hours=1)}
    assert not run._needs_agent(fresh)
    assert run._needs_agent({**fresh, "opened_at": now - timedelta(hours=7)})
    assert not run._needs_agent({**fresh, "opened_at": now - timedelta(hours=7), "attempts": 3})
    assert not run._needs_agent({**fresh, "opened_at": now - timedelta(hours=30), "attempts": 1,
                                 "last_attempt_at": now - timedelta(hours=2)})


def test_stale_reference_waits_for_files_being_written(monkeypatch):
    monkeypatch.setattr(checks, "dirty_paths", lambda root=None: {"docs/reference/CODE.md"})
    monkeypatch.setattr(checks, "docs_check", lambda: {"ok": False, "stale": ["docs/reference/CODE.md"]})
    called = []
    monkeypatch.setattr(repair.subprocess, "run", lambda *a, **k: called.append(a))
    assert repair.regenerate_docs("m") == {"applied": False, "deferred": True, "blocked": ["docs/reference/CODE.md"]}
    assert not called                                   # nothing regenerated over someone's work


def test_reference_regeneration_is_quiet():
    inc = _inc("fixed", outcome="fixed", quiet=True, apply={"applied": True})
    assert run._message(inc) is None


def test_no_reference_in_this_version_is_no_incident(monkeypatch):
    monkeypatch.setattr(checks, "docs_check", lambda: {})
    assert checks.docs() == []


def test_a_stale_reference_is_one_docs_incident_not_also_a_test_failure(monkeypatch, tmp_path):
    """2026-11-25 (incident 691): the reference test failed beside the deferred `docs` incident (generated files
    being someone's work in progress), and the repair agent was sent onto those files."""
    file, name = checks.REFERENCE_TEST.split("::")
    assert f"def {name}(" in (paths.ROOT / file).read_text()        # the skipped id is the real reference test
    monkeypatch.setattr(checks, "run_tests", lambda root: {"ok": False, "failures": {
        checks.REFERENCE_TEST: "AssertionError: stale", "tests/test_k.py::test_v": "AssertionError: x"}})
    monkeypatch.setattr(checks, "dirty_paths", lambda root=None: {"docs/reference/CODE.md"})
    for name in ("sources", "cycle", "providers", "credits", "padlocks"):
        monkeypatch.setattr(checks, name, lambda conn: [])
    monkeypatch.setattr(checks, "docs_check", lambda: {"ok": False, "stale": ["docs/reference/CODE.md"]})
    keys = [p["key"] for p in checks.detect(None)]
    assert keys == ["docs", "test:tests/test_k.py::test_v"]
    monkeypatch.setattr(checks, "docs_check", lambda: {"ok": True, "stale": []})   # current reference: the test counts
    assert f"test:{checks.REFERENCE_TEST}" in [p["key"] for p in checks.detect(None)]


def test_the_reference_test_is_not_still_broken_while_docs_follows_it(monkeypatch):
    monkeypatch.setattr(checks, "docs", lambda: [{"key": "docs", "kind": "docs_stale"}])
    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: pytest.fail("the docs incident owns it: no pytest"))
    assert not run.still_broken(None, {"kind": "test_failure", "subject": checks.REFERENCE_TEST})


def test_parametrised_test_ids_with_spaces_are_kept_whole(monkeypatch, tmp_path):
    out = ("FAILED tests/test_k.py::test_v[20 variantes en brouillon-budget-grok] - AssertionError: x\n"
           "ERROR tests/test_c.py\n")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, out, ""))
    assert checks.run_tests(tmp_path)["failures"] == {
        "tests/test_k.py::test_v[20 variantes en brouillon-budget-grok]": "AssertionError: x",
        "tests/test_c.py": "ERROR"}


def test_an_incident_out_of_agent_runs_goes_to_the_owner(monkeypatch):
    """2026-11-20: incidents stayed `open` forever after their last run (the count was read before its increment),
    so the owner never heard of them (AA source 15–17/11, five failing tests since 13/11)."""
    sets = []
    monkeypatch.setattr(run, "_set", lambda conn, inc, status, verdict=None, attempt=False: sets.append(status))
    monkeypatch.setattr(run.repair, "agent", lambda inc, tried: {"ok": False, "verdict": {"outcome": "unknown"}})
    now = datetime.now(timezone.utc)
    inc = {"incident_id": 7, "kind": "source_stale", "subject": "aa", "status": "open", "attempts": run.MAX_ATTEMPTS - 1,
           "last_attempt_at": now - timedelta(hours=13), "opened_at": now - timedelta(hours=40), "detail": {}}
    run._repair(None, inc, dry_run=False)
    assert sets[-1] == "needs_owner"                      # the last run failed: the owner is told
    sets.clear()
    stuck = {**inc, "attempts": run.MAX_ATTEMPTS}          # left `open` by the old code
    monkeypatch.setattr(run, "reread_source", lambda kind: {"ok": False})
    run.handle(None, stuck, [3])
    assert sets == ["needs_owner"]


def test_the_repair_agents_fixed_is_checked_before_anyone_believes_it(monkeypatch):
    """2026-11-20: the Router hands incidents to the guardians' common repair agent (coding/L3, dev rights)."""
    sets, told = [], []
    monkeypatch.setattr(run, "_set", lambda conn, inc, status, verdict=None, attempt=False:
                        sets.append(status) or inc.update(status=status, verdict=verdict or inc.get("verdict")))
    monkeypatch.setattr(run.repair, "agent", lambda inc, tried: told.append(tried) or {
        "ok": True, "poste": "coding/L3", "verdict": {"outcome": "fixed", "cause": "nouvelle page AA",
                                                       "summary_fr": "La page AA avait changé ; le lecteur suit."}})
    now = datetime.now(timezone.utc)
    inc = {"incident_id": 8, "kind": "source_stale", "subject": "aa", "status": "open", "attempts": 0,
           "opened_at": now - timedelta(hours=40), "detail": {}, "verdict": None}
    monkeypatch.setattr(run, "still_broken", lambda conn, i: True)
    v = run._repair(None, inc, dry_run=False)
    assert v["outcome"] == "failed" and "toujours en panne" in v["cause"] and sets[-1] == "open"
    monkeypatch.setattr(run, "still_broken", lambda conn, i: False)
    inc.update(attempts=0, status="open")
    v = run._repair(None, inc, dry_run=False)
    assert v["verified"] and sets[-1] == "fixed"
    assert "réparé tout seul" in run._message(inc) and "La page AA" in run._message(inc)
    assert "tentative précédente : failed" in told[1]      # the second run knows what the first one found


def test_the_router_hands_the_incident_to_the_common_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(repair.instance, "state_file", lambda name: tmp_path / name)
    seen = []
    def fake_run(cmd, **k):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"verdict": {"outcome": "external"}, "poste": "coding/L3",
                                                                "engine": {"ok": True, "walter_session": "w-1"}}), "")
    monkeypatch.setattr(repair.subprocess, "run", fake_run)
    out = repair.agent({"incident_id": 3, "key": "provider:kie", "kind": "provider_down", "subject": "kie",
                        "detail": {"probe": "HTTP 503"}, "opened_at": None})
    assert seen[0][:4] == ["walter-guardian", "repair", "--module", "router"] and "--wait" in seen[0]
    assert out["verdict"]["outcome"] == "external" and out["poste"] == "coding/L3" and out["ok"]
    sent = json.loads((tmp_path / "guardian" / "repair" / "3.json").read_text())
    assert sent["incident"]["key"] == "provider:kie" and sent["incident"]["module"] == "router"


def test_library_page_is_republished_only_when_it_says_something_new():
    from walter_router.interface import library
    page = "<p>Claude Pro, quota {q} %</p><footer>Page générée le {t}.</footer>"
    old = page.format(q=48, t="18/11/2026, 19:32 UTC")
    assert not library.differs(page.format(q=48, t="20/11/2026, 09:50 UTC"), old)
    assert library.differs(page.format(q=82, t="20/11/2026, 09:50 UTC"), old)
    assert library.differs(old, None)


def test_an_unreadable_benchmark_is_named_as_such_never_as_a_provider():
    """2026-11-22 (owner, « pourquoi je viens de recevoir ça ? »): « arena ne répond plus… passe par les autres
    fournisseurs () » — Arena is a ranking, not a provider, and the empty brackets said nothing."""
    inc = {**_inc("external", 50), "kind": "source_error", "subject": "arena",
           "detail": {"error": "incomplete collection"}, "verdict": {"cause": "la sortie du Mac était fermée (VPN)"}}
    msg = run._message(inc)
    assert "benchmark illisible" in msg and "Arena (LMArena)" in msg and "fournisseur" not in msg
    assert "VPN" in msg and "()" not in msg
    assert "()" not in run._message({**_inc("external", 50), "detail": {}})


def test_an_outside_source_outage_is_read_again_every_pass(monkeypatch):
    seen = []
    monkeypatch.setattr(run, "reread_source", lambda kind: seen.append(kind) or {"ok": True, "snapshot_id": 1})
    monkeypatch.setattr(run, "_set", lambda conn, inc, status, verdict=None, **kw: seen.append(status))
    inc = {"kind": "source_error", "subject": "arena", "status": "external", "attempts": 1, "detail": {},
           "opened_at": datetime.now(timezone.utc) - timedelta(hours=50), "last_attempt_at": None}
    run.handle(None, inc, [3])
    assert seen == ["arena", "resolved"]
