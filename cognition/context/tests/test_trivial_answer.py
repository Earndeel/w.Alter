"""Lot 2 (2026-11-07): trivial messages answered without a model; the answer is bound to the owner's message."""
from datetime import datetime, timezone

import pytest

from walter_context.plan import ContextPlan, ContractError, ThreadChoice
from walter_context.preflight import Request, fast_path
from walter_context.preflight.__main__ import requested
from walter_context.preflight.trivial import answer


@pytest.mark.parametrize("text,expected", [("combien font 3 + 4", "3 + 4 = 7"), ("12*7", "12*7 = 84"),
                                           ("15 % de 80", "15 % de 80 = 12"), ("combien font 2,5 x 4 ?", "2,5 x 4 = 10"),
                                           ("1 000 000 * 3", "1 000 000 * 3 = 3 000 000")])
def test_calculations_are_exact(text, expected):
    assert answer(text, None) == expected


@pytest.mark.parametrize("text", ["10/0", "1e3*2", "combien font 100 €", "2**999", "__import__('os')", "test"])
def test_anything_unclear_goes_to_the_model(text):
    assert answer(text, "Europe/Paris") is None


def test_time_names_its_zone_and_needs_one():
    at = datetime(2026, 11, 7, 9, 5, tzinfo=timezone.utc)
    assert answer("quelle heure est-il ?", "Asia/Bangkok", at) == "Il est 16 h 05 (heure de Bangkok)."
    assert answer("on est quel jour", "Europe/Paris", at) == "Nous sommes le samedi 7 novembre 2026 (heure de Paris)."
    assert answer("quelle heure est-il", None, at) is None


def test_only_a_trivial_plan_may_carry_an_answer_and_it_is_bound_to_the_message():
    plan = fast_path(Request(turn_id="t", message="12*7"))
    assert plan.fast_path == "trivial" and plan.answer == "12*7 = 84"
    req = requested(plan.to_dict(), " 12*7 ")
    assert req["answer"] == "12*7 = 84" and len(req["message_sha"]) == 64 and req["task"] == "general"
    with pytest.raises(ContractError):
        ContextPlan(turn_id="t", thread=ThreadChoice(id=None, new=True), act="new", level="L1", answer="x").validate()
    assert "answer" not in requested(ContextPlan(turn_id="t", thread=ThreadChoice(id=None, new=True), act="new",
                                                 level="L1").to_dict(), "test")


def test_machine_turn_gets_one_tier_below():
    from walter_context.preflight.__main__ import requested
    plan = {"model_profile": {"task": "document", "level": "L2"}}
    assert requested(plan, "x")["level"] == "L2"
    assert requested(plan, "x", "machine")["level"] == "L1"
    assert requested({"model_profile": {"task": "general", "level": "L1"}}, "x", "machine")["level"] == "L1"
