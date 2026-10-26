"""New-skill judgement: only blocking issues reject; minor ones are kept as notes; the full list reaches git."""
from walter_skills.curation.operators import issues_body, triage


def test_minor_issues_do_not_reject():
    v = triage({"ok": False, "issues": ["MINOR: --year falls back to all results", "minor: wording"]})
    assert v["ok"] and v["blocking"] == [] and len(v["minor"]) == 2


def test_blocking_issue_rejects():
    v = triage({"ok": True, "issues": ["BLOCKING: contains an API key", "MINOR: style"]})
    assert not v["ok"] and v["blocking"] == ["BLOCKING: contains an API key"] and v["minor"] == ["MINOR: style"]


def test_unprefixed_issue_or_silent_refusal_fails_closed():
    assert not triage({"ok": True, "issues": ["the command is wrong"]})["ok"]
    assert not triage({"ok": False, "issues": []})["ok"]
    assert triage({"ok": True, "issues": []})["ok"]
    assert triage(None) is None


def test_commit_body_lists_every_remark_in_full():
    long = "MINOR: " + "x" * 400
    body = issues_body({"issues": ["BLOCKING: a", long]})
    assert "- BLOCKING: a" in body and long in body
    assert issues_body({"issues": []}) == ""
