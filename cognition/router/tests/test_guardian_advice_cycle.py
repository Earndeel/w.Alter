"""48 h cycle step 2: one Router agent (2026-11-20, owner: the cycle analyst and the advisor merged). At the cycle it
also checks sources and names; the Router applies its name links through the validated add and writes the report.
History: 2026-11-13 the analyst became a Walter Engine delegation (before, a Hermes loop)."""
from datetime import datetime, timezone

from walter_router.guardian import advice as advisor

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def _add(conn, key, model_id, reason, origin):
    if model_id == "unscored":
        raise ValueError("unscored has no scores: linking to it gains nothing")
    return {"added": key, "model_id": model_id}


def _report(tmp_path, verdict, ran, add=_add):
    out = advisor.cycle_report(None, verdict, ran, add=add, log_dir=tmp_path, now=NOW)
    return out, (tmp_path / "analysis-20261113.md").read_text()


def test_the_router_applies_the_valid_links_and_reports_the_refused_ones(tmp_path):
    v = {"summary_fr": "s", "proposals": [], "report_fr": "Deux candidats.",
         "aliases": [{"key": "hailuo-3", "model_id": "minimax-h3", "reason": "https://example.org same model"},
                     {"key": "foo", "model_id": "unscored", "reason": "a reason long enough to pass"},
                     {"key": "bad"}],
         "_kept": [{"title_fr": "Relais L3", "new": True}, {"title_fr": "Mauvais", "refused": "pas de route"}]}
    out, report = _report(tmp_path, v, {"ok": True, "output": "…"})
    assert out["added"] == ["hailuo-3"] and out["refused"] == 1
    assert "Deux candidats." in report and "hailuo-3 → minimax-h3" in report
    assert "foo → unscored : unscored has no scores" in report
    assert "- Relais L3" in report and "Mauvais (refusée : pas de route)" in report


def test_no_answer_or_an_unparsable_one_changes_nothing_and_keeps_the_cycle_going(tmp_path):
    touched = []
    for ran in ({"ok": False, "error": "URLError"}, {"ok": True, "output": "je n'ai pas pu"}):
        out, report = _report(tmp_path, None, ran, add=lambda *a: touched.append(a))
        assert out["added"] == [] and "Rien n'a été appliqué" in report
    assert touched == []


def test_the_cycle_brief_carries_the_names_duty_the_deadline_and_no_code_reading():
    st = {"trigger": "cycle", "cycle": {"review": {"unmatched_candidates": [{"model_id": "hailuo-3"}]}}}
    text = advisor.brief(st, budget=1100, start=NOW.timestamp())
    assert '"hailuo-3"' in text and '"aliases"' in text and "report_fr" in text
    assert "ne lis PAS le code" in text and "conclus avant 00:13 UTC" in text and f"{advisor.MAX_CHECKS} vérifications" in text
    owner = advisor.brief({"trigger": "owner"}, budget=1100, start=NOW.timestamp())
    assert "report_fr" not in owner and "ne lis PAS le code" in owner


def test_the_owners_own_rules_for_the_guardian_come_last_and_win(tmp_path, monkeypatch):
    f = tmp_path / "guardian-rules.md"
    f.write_text("# Règles\n\nExplication.\n- Ne me propose jamais Fable en L1.\n-\n")
    monkeypatch.setattr(advisor.instance, "config_path", lambda name: f)
    text = advisor.brief({"trigger": "owner"}, budget=1100, start=NOW.timestamp())
    assert "- Ne me propose jamais Fable en L1." in text and "Explication." not in text
    assert text.index("Ne me propose jamais") < text.index("## État")
    assert "{{" not in text and "Consignes du guardian" not in text     # placeholders filled, file header for humans
