"""48 h cycle step 2 (2026-11-13): the research agent is one Walter Engine delegation, no longer a Hermes loop.
The agent only reads and answers; the Router applies its name links through the validated add and writes the report."""
import json
from datetime import datetime, timezone

from walter_router.research.agent import run as agent

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
DATA = {"review": {"unmatched_candidates": [{"model_id": "hailuo-3", "closest": "minimax-h3"}]}, "health": {"ok": True},
        "aliases": {}}


def _run(tmp_path, answer, add=None):
    calls = []

    def delegate(prompt, source, timeout):
        calls.append({"prompt": prompt, "source": source, "timeout": timeout})
        return answer

    def default_add(conn, key, model_id, reason, origin):
        if model_id == "unscored":
            raise ValueError("unscored has no scores: linking to it gains nothing")
        return {"added": key, "model_id": model_id}
    out = agent.run(None, delegate=delegate, gather=lambda c: DATA, add=add or default_add, log_dir=tmp_path, now=NOW)
    return out, calls, (tmp_path / "analysis-20261113.md").read_text()


def test_the_agent_is_asked_through_the_engine_with_the_cycle_data_and_no_shell(tmp_path):
    answer = json.dumps({"aliases": [], "report": "Sources à jour."})
    out, calls, report = _run(tmp_path, answer)
    assert out["ok"] and out["runtime"] == "walter-engine" and len(calls) == 1
    p = calls[0]["prompt"]
    assert calls[0]["source"] == "walter-router-analysis"
    assert '"hailuo-3"' in p and "{{" not in p
    assert "alias-add" not in p and "pas de commande shell" in p      # nothing for the agent to run itself
    assert "Sources à jour." in report and "- aucun" in report


def test_the_router_applies_the_valid_links_and_reports_the_refused_ones(tmp_path):
    answer = "```json\n" + json.dumps({"aliases": [
        {"key": "hailuo-3", "model_id": "minimax-h3", "reason": "https://example.org same model, official page"},
        {"key": "foo", "model_id": "unscored", "reason": "a reason long enough to pass"},
        {"key": "bad"}], "report": "Deux candidats."}) + "\n```"
    out, _, report = _run(tmp_path, answer)
    assert out["added"] == ["hailuo-3"] and out["refused"] == 1
    assert "hailuo-3 → minimax-h3" in report and "foo → unscored : unscored has no scores" in report


def test_no_answer_or_an_unparsable_one_changes_nothing_and_keeps_the_cycle_going(tmp_path):
    touched = []
    for answer, error in ((None, "no_answer"), ("je n'ai pas pu", "unparsable_answer")):
        out, _, report = _run(tmp_path, answer, add=lambda *a: touched.append(a))
        assert out["ok"] is False and out["error"] == error and "Rien n'a été appliqué" in report
    assert touched == []
