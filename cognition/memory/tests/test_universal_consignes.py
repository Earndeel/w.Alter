"""The universal consignes in the reconsolidation (owner 2026-11-26): they belong to no subject, so the subject pass
never saw them. Proposals validated like the subjects' ones, plus the portée and the contradictions; an empty model
answer is a failure, never « nothing to propose »."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import consolidate, processing

NOW = datetime.now(timezone.utc)


def _items():
    return [{"id": str(uuid.uuid4()), "kind": "constraint", "content": t, "stage": None, "scope": "durable",
             "epistemic": "stated_owner", "valid_from": NOW - timedelta(days=d), "created_at": NOW - timedelta(days=d),
             "privacy_class": "cloud_allowed"}
            for d, t in ((3, "Vouvoie Monsieur."), (2, "Vouvoie toujours Monsieur."), (1, "N'ouvre pas de fenêtre sur le Mac."))]


@pytest.fixture
def scripted(monkeypatch):
    items = _items()
    monkeypatch.setattr(consolidate, "_universal_items", lambda conn: items)
    monkeypatch.setattr(processing, "decide_once", lambda name, v, key, call, **kw: (call()[0], False))
    return items


def test_proposals_are_validated_and_recorded_only(scripted):
    a, b, c = (i["id"][:8] for i in scripted)

    def chat(messages, **kw):
        assert "UNIVERSELLES" in messages[0]["content"]
        return {"model": "scripted", "content": json.dumps({
            "merge": [[a, b], ["zzzzzzzz", a]], "supersede": [{"old": b, "new": a, "why": "plus ancienne"}],
            "reach": [{"id": c, "reach": "situation", "on": "le Mac", "why": "un outil"}, {"id": a, "reach": "galaxie"}],
            "contradiction": [{"ids": [a, c], "why": "x"}]})}
    r = consolidate.reconsolidate_universal(chat=chat, apply=False)
    p = r["proposals"]
    assert p["merge"] == [[scripted[0]["id"], scripted[1]["id"]]]          # an unknown id makes no group
    assert p["supersede"] == []                                             # the replacing consigne must be newer
    assert [x["id"] for x in p["reach"]] == [scripted[2]["id"]]             # a known, narrower portée only
    assert p["contradiction"][0]["ids"] == [scripted[0]["id"], scripted[2]["id"]]
    assert r["applied"] is False


def test_an_empty_answer_is_a_failure_not_nothing_to_propose(scripted):
    with pytest.raises(RuntimeError):
        consolidate.reconsolidate_universal(chat=lambda messages, **kw: {"model": "scripted", "content": ""},
                                            apply=False)


def test_a_replacement_the_owner_refused_is_never_proposed_again(scripted):
    a, b, c = (i["id"][:8] for i in scripted)
    scripted[0]["refused"] = [{"by": scripted[1]["id"], "why": "complémentaires"}]

    def chat(messages, **kw):
        return {"model": "scripted", "content": json.dumps({
            "supersede": [{"old": a, "new": b, "why": "x"}, {"old": a, "new": c, "why": "y"}]})}
    p = consolidate.reconsolidate_universal(chat=chat, apply=False)["proposals"]
    assert p["supersede"] == [{"old": scripted[0]["id"], "new": scripted[2]["id"], "why": "y"}]


def test_owner_decision_refuses_items_not_in_force_and_is_a_dry_run_by_default():
    r = consolidate.owner_universal({"keep": [{"keep": str(uuid.uuid4()), "drop": [str(uuid.uuid4())]}]},
                                    evidence=[], decided_by="test", tag="test-owner-universal")
    assert r["error"] == "not in force" and r["applied"] is False
