"""Rules that settle a triage decision before any model call (2026-11-05)."""
from walter_memory import triage

R = {"muted_threads": ["!muted"], "vip_threads": ["!vip"], "vip_people": ["Maman"], "silent_group_networks": ["line"]}


def ctx(**k):
    return {"thread_kind": "group", "network": "line", "monsieur_messages_30d": 0, "monsieur_mentioned": False, **k}


def ev(thread="!g", sender="x"):
    return {"thread_id": thread, "payload": {"sender_name": sender}}


def test_silent_line_group_is_ignored_without_model():
    assert triage._without_model(R, ev(), ctx())[0] == "ignore"
    assert triage._without_model(R, ev(), ctx(network="LINE"))[0] == "ignore"


def test_line_group_still_goes_to_the_model_when_monsieur_is_involved():
    assert triage._without_model(R, ev(), ctx(monsieur_mentioned=True)) is None
    assert triage._without_model(R, ev(), ctx(monsieur_messages_30d=3)) is None


def test_other_cases_go_to_the_model():
    assert triage._without_model(R, ev(), ctx(thread_kind="single")) is None
    assert triage._without_model(R, ev(), ctx(network="WhatsApp")) is None
    assert triage._without_model(R, ev("!vip"), ctx()) is None
    assert triage._without_model(R, ev(sender="Maman"), ctx()) is None
    assert triage._without_model({**R, "silent_group_networks": []}, ev(), ctx()) is None


def test_muted_thread_is_remembered_without_model():
    assert triage._without_model(R, ev("!muted"), ctx(thread_kind="single")) == ("remember", "muted thread")
