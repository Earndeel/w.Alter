"""Guardian (2026-10-26): detection rules, the agent's verdict, the gates and the landing rules of a patch."""
from __future__ import annotations

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


def test_verdict_is_the_last_json_with_an_outcome():
    out = 'Investigated {"a": 1}.\n```json\n{"outcome": "fixed", "cause": "page redesign", "changes": ["x"]}\n```'
    assert repair.verdict_of(out)["cause"] == "page redesign"
    assert repair.verdict_of("no verdict here")["outcome"] == "unknown"


def _workspace(tmp_path, files, edits):
    module = _repo(tmp_path / "ws", files)
    for name, text in edits.items():
        if text is None:
            (module / name).unlink()
        else:
            (module / name).parent.mkdir(parents=True, exist_ok=True)
            (module / name).write_text(text)
    return module


def test_gates_refuse_scope_weakened_tests_and_new_failures(tmp_path, monkeypatch):
    files = {"research/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert 1\n    assert 2\n",
             "config/knowledge.json": "{}"}
    module = _workspace(tmp_path, files, {"research/a.py": "x = 2\n", "config/knowledge.json": '{"pin": 1}',
                                          "tests/test_a.py": "import pytest\n@pytest.mark.skip\ndef test_a():\n    assert 1\n"})
    monkeypatch.setattr(checks, "run_tests", lambda root: {"failures": {"tests/test_b.py::test_b": "x"}})
    g = repair.gates(module, {"kind": "test_failure", "subject": "tests/test_a.py::test_a"}, {"failures": {}})
    text = " | ".join(g["reasons"])
    assert not g["ok"]
    assert "config/knowledge.json" in text and "fewer assertions" in text and "skip/xfail" in text
    assert "tests/test_b.py::test_b" in text


def test_gates_pass_a_clean_fix_of_the_failing_test(tmp_path, monkeypatch):
    files = {"interface/page.py": "WORD = 'fidélité'\n", "tests/test_p.py": "def test_p():\n    assert 1\n"}
    module = _workspace(tmp_path, files, {"interface/page.py": "WORD = 'loyalty'\n"})
    monkeypatch.setattr(checks, "run_tests", lambda root: {"failures": {"tests/test_old.py::t": "x"}})
    g = repair.gates(module, {"kind": "test_failure", "subject": "tests/test_p.py::test_p"},
                     {"failures": {"tests/test_p.py::test_p": "x", "tests/test_old.py::t": "x"}})
    assert g["ok"], g["reasons"]
    assert g["files"] == ["interface/page.py"]


def test_apply_lands_only_on_untouched_files_and_commits_just_them(tmp_path, monkeypatch):
    files = {"research/a.py": "x = 1\n", "research/b.py": "y = 1\n", "serve/other.py": "z = 1\n"}
    live = _repo(tmp_path / "live", files)
    monkeypatch.setattr(paths, "ROOT", live)
    (live / "serve/other.py").write_text("z = 2  # someone else's work in progress\n")

    module = _workspace(tmp_path, files, {"research/a.py": "x = 2\n"})
    repair.changed_files(module)
    landed = repair.apply(module, ["research/a.py"], [], "Guardian: test")
    assert landed["applied"] and (live / "research/a.py").read_text() == "x = 2\n"
    committed = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=live, capture_output=True,
                               text=True).stdout.split()
    assert committed == ["research/a.py"]
    assert (live / "serve/other.py").read_text().startswith("z = 2")      # left alone, still uncommitted

    (live / "research/b.py").write_text("y = 5\n")                          # edited by someone meanwhile
    module2 = _workspace(tmp_path / "2", {**files, "research/a.py": "x = 2\n"}, {"research/b.py": "y = 2\n"})
    repair.changed_files(module2)
    later = repair.apply(module2, ["research/b.py"], [], "Guardian: test")
    assert later == {"applied": False, "deferred": True, "blocked": ["research/b.py"]}
    assert (live / "research/b.py").read_text() == "y = 5\n"


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


def test_parametrised_test_ids_with_spaces_are_kept_whole(monkeypatch, tmp_path):
    out = ("FAILED tests/test_k.py::test_v[20 variantes en brouillon-budget-grok] - AssertionError: x\n"
           "ERROR tests/test_c.py\n")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, out, ""))
    assert checks.run_tests(tmp_path)["failures"] == {
        "tests/test_k.py::test_v[20 variantes en brouillon-budget-grok]": "AssertionError: x",
        "tests/test_c.py": "ERROR"}
