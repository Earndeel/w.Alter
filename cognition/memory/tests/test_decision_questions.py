"""2026-11-13: Walter Router's decision bench reads the triage questions from this module (no copy that could drift)."""
import json

from walter_memory import cli, triage


def test_decision_questions_prints_the_triage_questions_as_production_asks_them(capsys):
    cli.main(["decision-questions", "triage"])
    out = json.loads(capsys.readouterr().out)
    assert out["questions"] == triage.QUESTIONS and "messages" in out["state_keys"]
