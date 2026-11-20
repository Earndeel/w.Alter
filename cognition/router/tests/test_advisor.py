"""2026-11-20 (owner): « le router doit avoir un vrai agent intelligent qui s'occupe de comprendre les tenants et les
aboutissants » — the advisor agent reads the whole picture, proposes; the owner decides on Telegram."""
import json

import pytest

from walter_router.analysis import advisor, alerts, knowledge, telegram
from walter_router.serve import choose
from walter_router.store import db


@pytest.fixture
def conn():
    with db.connect() as c:
        if choose.latest_run(c) is None:
            pytest.skip("no refresh yet")
        yield c
        c.rollback()


def test_verdict_is_the_last_json_object_with_proposals():
    out = 'je regarde… {"x": 1}\nfin\n{"summary_fr": "ok", "proposals": [{"title_fr": "t", "action": {"op": "note"}}]}'
    assert advisor.verdict_of(out)["summary_fr"] == "ok"
    assert advisor.verdict_of("aucun json") is None


def test_unknown_or_unroutable_actions_are_refused(conn):
    assert advisor.validate(conn, {"op": "rm -rf"}) == "action inconnue"
    assert advisor.validate(conn, {"op": "set_quota_fallback", "level": "L9", "pin": "x/y"}) == "niveau inconnu"
    assert "route" in advisor.validate(conn, {"op": "set_quota_fallback", "level": "L3", "pin": "no-such-model/max"})
    assert advisor.validate(conn, {"op": "set_lock", "task": "no-such-task", "role": "x", "locked": True}) == "tâche inconnue"
    assert advisor.validate(conn, {"op": "note"}) is None


def test_a_level_cannot_be_its_own_quota_substitute(conn):
    pin = knowledge.load()["levels"]["general"]["L3"]["pin"]
    assert advisor.validate(conn, {"op": "set_quota_fallback", "level": "L3", "pin": pin}) is not None


def test_proposals_become_advice_alerts_sent_with_apply_buttons(conn):
    conn.execute("delete from models.alerts where kind = 'advice'")
    v = {"summary_fr": "s", "proposals": [
        {"title_fr": "Info", "why_fr": "parce que", "consequences_fr": "rien", "action": {"op": "note"}},
        {"title_fr": "Mauvais", "action": {"op": "set_quota_fallback", "level": "L3", "pin": "no-such-model/max"}}]}
    kept = advisor.record(conn, v, {"trigger": "test", "at": "now"})
    assert kept[0]["new"] and kept[1]["refused"]
    a = conn.execute("select * from models.alerts where kind = 'advice'").fetchone()
    assert a["status"] == "open" and a in alerts.pending(conn)
    text = telegram.render_each([a], conn)[0]
    assert "Conseil du Router" in text and "parce que" in text
    assert [b["text"] for b in telegram.keyboard(conn, [a])[0]] == ["👁️ Vu"]          # a note: nothing to apply
    again = advisor.record(conn, v, {"trigger": "test", "at": "later"})
    assert not again[0]["new"]                                                     # same action = same alert


def test_adopting_a_quota_substitute_writes_the_declared_level(conn, monkeypatch):
    written = {}
    monkeypatch.setattr(advisor, "validate", lambda c, a: None)
    monkeypatch.setattr(knowledge, "set_level", lambda *a, **k: written.update(args=a, kw=k))
    out = advisor.apply(conn, {"op": "set_quota_fallback", "level": "L3", "pin": "some-model/max"}, "test")
    assert out["applied"] and written["kw"]["when_quota_spent"] == written["kw"]["fallback"] == "some-model/max"
    assert written["args"][2] == knowledge.load()["levels"]["general"]["L3"]["pin"]     # the tier itself is unchanged


def test_launch_never_runs_from_tests():
    assert advisor.launch("cycle") is False


def test_state_holds_the_declared_tiers_and_the_owner_rules(conn):
    st = advisor.state(conn, "test")
    assert set(st["declared_text_tiers"]) == {"L1", "L2", "L3"}
    assert "pin_now" in st["declared_text_tiers"]["L3"] and st["tier_rules"]
    assert len(advisor.brief(st)) < 120_000
    json.dumps(st, default=str)


def test_the_cycle_state_holds_the_former_analysts_facts(conn):
    st = advisor.state(conn, "cycle")
    assert {"review", "health", "name_links_already_made"} <= set(st["cycle"])
    assert "tiers" not in st["cycle"]["review"]                  # already in the state, with more detail
    assert len(advisor.brief(st)) < 120_000
    assert "cycle" not in advisor.state(conn, "owner")


def test_the_run_fits_the_cycle_step():
    assert advisor.BUDGET + 120 < 1300                           # bin/walter-router-cycle: timeout 1300 analyze


def test_two_notes_of_one_run_are_two_alerts(conn):
    conn.execute("delete from models.alerts where kind = 'advice'")
    v = {"summary_fr": "s", "proposals": [{"title_fr": "Recharger OpenRouter", "action": {"op": "note"}},
                                          {"title_fr": "ChatGPT Plus à 85 %", "action": {"op": "note"}}]}
    kept = advisor.record(conn, v, {"trigger": "test", "at": "now"})
    assert [k["new"] for k in kept] == [True, True]
    assert conn.execute("select count(*) as n from models.alerts where kind = 'advice'").fetchone()["n"] == 2
