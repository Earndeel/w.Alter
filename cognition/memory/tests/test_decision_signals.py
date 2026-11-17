"""Walter Decision 2.0 (2026-11-17): Memory's questions are its declared signals (manifest/decisions.json) — triage
asks by occasion `incoming`, disclosure by `outgoing`; the values read (a deadline, an amount, the days committed
to) feed their rules; the people a message names resolve against the people Monsieur talks with. Offline."""
from datetime import datetime

import pytest

from walter_memory import context, disclosure, llm, triage


def test_the_triage_questions_are_the_declared_incoming_judgements():
    inc = triage.signals("incoming")
    assert set(triage.QUESTIONS) == {"action", "urgency", "category", "needs_reply"}
    assert all(triage.QUESTIONS[k] == inc[k]["question"] for k in triage.QUESTIONS)
    assert {k for k, s in inc.items() if s.get("when")} == {"deadline", "amount"}       # readings, on a cue only
    assert inc["action"]["required"] is True


def test_values_read_are_kept_as_values_and_only_when_sure():
    sig = {"memory.deadline": {"type": "date", "date": "2026-11-18", "text": "demain", "found": 0.93},
           "memory.amount": {"type": "number", "number": 120.0, "unit": "EUR", "text": "120 €", "found": 0.9}}
    assert triage.observed(sig) == {"deadline": "2026-11-18", "amount": {"value": 120.0, "unit": "EUR"}}
    assert triage.observed({"memory.deadline": {"date": "2026-11-18", "found": 0.2}}) == {}
    assert triage.observed({"memory.amount": None, "memory.deadline": {"date": "jeudi"}}) == {}


R = {"vip_threads": [], "vip_people": [], "email_categories_never_notified": [], "silence_hours": [23, 7],
     "max_notifications_per_hour": 10}
EV = {"thread_id": "!t", "payload": {}, "source": "beeper"}
CTX = {"monsieur_answered_after": False, "thread_kind": "single", "monsieur_mentioned": False}
NOON = datetime(2026, 11, 17, 12, 0)


def test_a_deadline_within_a_day_is_not_whenever():
    d = {"action": "notify", "urgency": "later", "category": "admin", "deadline": "2026-11-18"}
    assert triage._apply_rules(R, EV, CTX, d, NOON, 0) == ("notify", "deadline within a day")
    assert d["urgency"] == "today"
    far = {"action": "notify", "urgency": "later", "category": "admin", "deadline": "2026-11-25"}
    triage._apply_rules(R, EV, CTX, far, NOON, 0)
    assert far["urgency"] == "later"


def test_a_payment_is_never_ignored_as_noise():
    d = {"action": "ignore", "urgency": "later", "category": "finance", "amount": {"value": 89.9, "unit": "EUR"}}
    assert triage._apply_rules(R, EV, CTX, d, NOON, 0) == ("remember", "amount to pay or receive: kept")
    promo = {"action": "ignore", "urgency": "later", "category": "promo", "amount": {"value": 9.9, "unit": "EUR"}}
    assert triage._apply_rules(R, EV, CTX, promo, NOON, 0)[0] == "ignore"


def test_an_outgoing_commitment_says_the_day_and_the_amount(monkeypatch):
    seen = {}

    def decide(state, questions, **kw):
        seen.update(kw, questions=questions)
        return {"model": "fake", "signals": {
            "memory.commits": {"choice": "yes", "confidence": 0.9},
            "memory.commit_when": {"spans": [{"text": "samedi", "date": "2026-11-21", "found": 0.9},
                                             {"text": "plus tard", "found": 0.8}]},
            "memory.commit_amount": {"number": 300, "found": 0.95}}}
    monkeypatch.setattr(llm, "decide", decide)
    monkeypatch.setattr("walter_memory.flows.tz", lambda: __import__("zoneinfo").ZoneInfo("Europe/Paris"))
    c = disclosure._commitment("Ok pour samedi, je te rembourse les 300 euros")
    assert c["when"] == ["2026-11-21"] and c["amount"] == 300 and c["confidence"] == 0.9
    assert seen["occasion"] == "outgoing" and seen["facts"] == ["pattern.commitment"] and seen["questions"] is None
    assert seen["focus"] == "message" and len(seen["now"]) == 10


def test_a_sure_no_releases_a_meeting_word_but_never_money(monkeypatch):
    monkeypatch.setattr(llm, "decide", lambda *a, **k: {"model": "fake", "signals": {
        "memory.commits": {"choice": "no", "confidence": 0.95}}})
    monkeypatch.setattr("walter_memory.flows.tz", lambda: __import__("zoneinfo").ZoneInfo("Europe/Paris"))
    assert disclosure._commitment("On se voit demain ? Je te dis") is None          # meeting word, model sure: no
    assert disclosure._commitment("je te rembourse les 300 euros") is not None      # money: always asked


@pytest.fixture
def people(monkeypatch):
    known = [("sophie martin", "e1"), ("sophie", "e1"), ("sophie durand", "e2"), ("paul", "e3"), ("jean-marc", "e4")]
    monkeypatch.setattr(context, "_known_people", lambda: known)
    monkeypatch.setattr(context, "_card_lines", lambda eid: [f"- card {eid}"])


def test_names_read_in_a_message_resolve_to_one_person_or_are_said_ambiguous(people):
    r = context.resolve_people(["Sophie Martin", "Paul", "Sophie", "@jean-marc", "Zorglub"])
    assert r["matched"] == {"Sophie Martin": "e1", "Paul": "e3", "@jean-marc": "e4"}
    assert r["unknown"] == ["Zorglub"]
    assert context.resolve_people(["Sophie"], exclude=["e1"])["matched"] == {}     # « sophie » is e1's alias


def test_people_cards_skip_those_already_shown_and_never_name_the_candidates(people, monkeypatch):
    monkeypatch.setattr(context, "_known_people", lambda: [("sophie martin", "e1"), ("sophie durand", "e2"),
                                                           ("paul", "e3")])
    r = context.people_cards(["Sophie", "Paul"], exclude=["e3"])
    assert r["matched"] == [] and r["ambiguous"] == {"Sophie": 2}
    assert "2 personnes connues" in r["text"] and "martin" not in r["text"].lower()


def test_a_complementary_decision_sends_only_the_signals_it_asks(monkeypatch):
    sent = {}

    def structured(path, body, timeout):
        sent.update(body)
        return {"answers": {}, "signals": {"memory.resume": {"noul": 0.8}}, "trace": {"asked": ["memory.resume"]},
                "calls": []}
    monkeypatch.setattr(llm, "_structured", structured)
    monkeypatch.setattr(llm, "_book_calls", lambda *a, **k: None)
    r = llm.decide({"new_message": "on reprend ?"}, None, processor="walter-context-preflight",
                   privacy_class="cloud_allowed", occasion="turn", focus="new_message", ask=["memory.resume"])
    assert sent["ask"] == ["memory.resume"] and sent["occasion"] == "turn" and "questions" not in sent
    assert r["signals"] == {"memory.resume": {"noul": 0.8}}
