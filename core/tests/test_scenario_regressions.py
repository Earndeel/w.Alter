"""End-to-end acceptance against synthetic recorded runs, never a model or database."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("walter_scenario_test", str(ROOT / "bin/walter-scenario"))
spec = importlib.util.spec_from_loader(loader.name, loader)
S = importlib.util.module_from_spec(spec)
loader.exec_module(S)


def offer(product="americano", method="search_snippet"):
    return {"product": product, "price_thb": "inconnu", "volume": "inconnu", "source_url": "https://example.test/menu", "method": method}


def events(offers, read=False):
    rows = [{"type": "tool/call", "tool": "walter_browse", "call_id": "s", "text": json.dumps({"query": "menu"})},
            {"type": "tool/result", "tool": "walter_browse", "call_id": "s", "status": "ok", "text": json.dumps({"results": [{"url": "https://example.test/menu", "snippet": "menu"}]})}]
    if read:
        rows += [{"type": "tool/call", "tool": "walter_browse", "call_id": "p", "text": json.dumps({"url": "https://example.test/menu", "content_only": True})},
                 {"type": "tool/result", "tool": "walter_browse", "call_id": "p", "status": "ok", "text": json.dumps({"success": True, "records": [{"content": "menu"}]})}]
    return rows + [{"type": "assistant/message", "text": json.dumps({"offers": offers})}]


def task(status="ended", ok=True):
    return {"kind": "walter_run", "status": status, "result": {"ok": ok}, "session_id": "task/1"}


def fixture_run(monkeypatch, tmp_path, tasks, trace, attestor=None, scenario="e2e-minimal"):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    from walter_platform import qualification
    monkeypatch.setattr(qualification, "attest", attestor or (lambda *a: {"fixture": True}))
    monkeypatch.setattr(S, "step_hook", lambda *a: {})
    monkeypatch.setattr(S, "step_mcp", lambda *a: {"ok": True})
    monkeypatch.setattr(S, "step_harness", lambda *a: {"ok": True, "run_id": "fixture-run"})
    monkeypatch.setattr(S.runctx, "current", lambda *a: {"run_id": "fixture-run"})
    shown = {"run": {"status": "ended", "routing": {"applied": True}}, "tasks": tasks,
             "model_calls": [{"ok": True}], "links": [{"kind": "session", "ref": "task/1"}]}
    def fake_run(argv, **kw):
        data = trace if "timeline" in argv else shown
        if "timeline" in argv:
            limit = int(argv[argv.index("--max-chars")+1]) if "--max-chars" in argv else 600
            data = [{**row, "text": row.get("text", "")[:limit]} for row in data]
        return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
    monkeypatch.setattr(S.subprocess, "run", fake_run)
    return S.run(ROOT / "scenarios" / (scenario + ".yaml"))


def test_failed_task_and_missing_offers_cannot_qualify(tmp_path, monkeypatch):
    report = fixture_run(monkeypatch, tmp_path, [task("failed", False)], events([]))
    assert report["ok"] is False
    assert not (tmp_path / "state/scenarios/qualifications.json").exists()


def test_two_source_backed_offers_with_explicit_unknown_values_pass(tmp_path, monkeypatch):
    report = fixture_run(monkeypatch, tmp_path, [task()], events([offer(), offer("latte")]))
    assert report["ok"] is True


@pytest.mark.parametrize("offers,read", [([], False), ([offer()], False),
    ([offer(), offer()], False), ([{**offer(), "source_url": "https://invented.test"}, offer("latte")], False),
    ([{**offer(), "price_thb": None}, offer("latte")], False), ([offer(method="http"), offer("latte")], False)])
def test_incomplete_duplicate_invented_or_unread_sources_fail(tmp_path, monkeypatch, offers, read):
    assert fixture_run(monkeypatch, tmp_path, [task()], events(offers, read))["ok"] is False


def test_claimed_page_read_requires_successful_read_evidence(tmp_path, monkeypatch):
    assert fixture_run(monkeypatch, tmp_path, [task()], events([offer(method="http"), offer("latte", "http")], True))["ok"] is True


@pytest.mark.parametrize("calls,expected", [([], None), ([{"cost_usd": None}], None),
    ([{"cost_usd": 0.2}, {}], None), ([{"cost_usd": 0}], 0), ([{"cost_usd": 0.25}], 0.25),
    ([{"cost_usd": "nan"}], None)])
def test_unknown_cost_is_not_zero(calls, expected):
    assert S.metrics({"model_calls": calls})["cost_usd"] == expected


def test_sources_changed_during_execution_cannot_qualify(tmp_path, monkeypatch):
    revisions = iter(({"revision": "before"}, {"revision": "after"}))
    report = fixture_run(monkeypatch, tmp_path, [task()], events([offer(), offer("latte")]),
                         attestor=lambda *a: next(revisions))
    assert report["ok"] is True
    assert report["qualification_status"] == "not_attested"
    assert not (tmp_path / "state/scenarios/qualifications.json").exists()


def test_page_provenance_reads_full_record_instead_of_a_timeline_excerpt(tmp_path, monkeypatch):
    trace = events([offer(method="http"), offer("latte", "http")], read=True)
    for row in trace:
        if row.get("type") == "tool/result" and row.get("call_id") == "p":
            row["text"] = json.dumps({"success": True, "records": [{"content": "menu " * 500}]})
    assert fixture_run(monkeypatch, tmp_path, [task()], trace)["ok"] is True


def test_known_price_strings_are_rejected_instead_of_coerced(tmp_path, monkeypatch):
    offers = [{**offer(), "price_thb": "35"}, offer("latte")]
    assert fixture_run(monkeypatch, tmp_path, [task()], events(offers))["ok"] is False


@pytest.mark.parametrize("status,payload,expected", [
    ("failed", {"success": True, "records": [{"content": "menu"}]}, False),
    ("ok", {"success": False, "records": [{"content": "menu"}]}, False),
    ("ok", {"ok": False, "records": [{"content": "menu"}]}, False),
    ("ok", {"success": True, "records": [{"content": "menu"}]}, True),
    ("ok", {"success": True, "records": []}, False),
])
def test_dsh_browse_requires_successful_recorded_result(tmp_path, monkeypatch, status, payload, expected):
    trace = [{"type": "tool/call", "tool": "walter__walter_browse", "call_id": "browse-1",
              "text": json.dumps({"query": "menu"})},
             {"type": "tool/result", "tool": "walter__walter_browse", "call_id": "browse-1", "status": status,
              "text": json.dumps(payload)}]
    report = fixture_run(monkeypatch, tmp_path, [], trace, scenario="dsh-recherche")
    assert report["ok"] is expected
    assert (tmp_path / "state/scenarios/qualifications.json").exists() is expected


@pytest.mark.parametrize("name", ["walter_browse", "mcp__walter__walter_browse", "walter.walter_browse"])
def test_successful_browse_assertion_accepts_runtime_tool_prefixes(monkeypatch, name):
    trace = events([])[:2]
    for row in trace:
        row["tool"] = name
    monkeypatch.setattr(S, "_session_events", lambda session: trace)
    ok, _ = S.check({"tool_succeeded": "walter_browse"}, {"links": [{"kind": "session", "ref": "dsh/session"}]})
    assert ok


@pytest.mark.parametrize("trace", [
    [{"type": "tool/call", "tool": "walter_browse", "call_id": "s", "text": '{"query":"menu"}'}],
    [{"type": "tool/result", "tool": "walter_browse", "call_id": "orphan", "status": "ok",
      "text": '{"success":true,"records":[{"content":"menu"}]}'}],
    [{"type": "tool/call", "tool": "walter_browse", "text": '{"query":"menu"}'},
     {"type": "tool/result", "tool": "walter_browse", "status": "ok",
      "text": '{"success":true,"records":[{"content":"menu"}]}'}],
])
def test_call_without_result_or_result_without_call_cannot_prove_browse(monkeypatch, trace):
    monkeypatch.setattr(S, "_session_events", lambda session: trace)
    ok, _ = S.check({"tool_succeeded": "walter_browse"}, {"links": [{"kind": "session", "ref": "dsh/session"}]})
    assert not ok


@pytest.mark.parametrize("status,success,expected", [("ok", True, True), ("ok", False, False),
                                                    ("failed", True, False)])
def test_dsh_native_result_inherits_browse_identity_only_from_matching_call(tmp_path, monkeypatch,
                                                                          status, success, expected):
    # Real DSH canonical logs name tool/call but leave tool/result.tool null.
    # Identifiers and public search content are reduced to a local fixture.
    trace = [{"type": "tool/call", "tool": "mcp__walter__walter_browse", "call_id": "toolu_fixture",
              "status": None, "text": '{"query":"menu"}'},
             {"type": "tool/result", "tool": None, "call_id": "toolu_fixture", "status": status,
              "text": json.dumps({"success": success, "query": "menu", "count": 1,
                                  "results": [{"title": "Menu", "url": "https://example.test/menu"}],
                                  "backend": "brave", "elapsed_ms": 10, "error": None,
                                  "objective": "search", "router_exit_code": 0})}]
    report = fixture_run(monkeypatch, tmp_path, [], trace, scenario="dsh-recherche")
    assert report["ok"] is expected
    assert (tmp_path / "state/scenarios/qualifications.json").exists() is expected


def test_explicitly_different_result_tool_cannot_inherit_browse_identity(monkeypatch):
    trace = events([])[:2]
    trace[1]["tool"] = "other_tool"
    monkeypatch.setattr(S, "_session_events", lambda session: trace)
    ok, _ = S.check({"tool_succeeded": "walter_browse"}, {"links": [{"kind": "session", "ref": "dsh/session"}]})
    assert not ok
