"""27/11/2026 (Monsieur, « quels sont mes derniers messages reçus ? »): the information the intent needs comes before
historic records within the L0 budget; a chronological question is read in order from Memory, without the early
rerank; the level budgets are unchanged."""
import sys
import threading
import time
import types

from walter_context import retrieval
from walter_context.assembly import pack
from walter_context.plan import ContextPlan, ThreadChoice


def plan(level="L0", personal=("history",), horizons=("instant",), observations=None, caps=("tools", "memory")):
    return ContextPlan(turn_id="t", thread=ThreadChoice(None, True, 0.5), act="new", level=level,
                       capabilities=list(caps), horizons=list(horizons), personal=list(personal),
                       observations=dict(observations or {}))


def fake_memory(monkeypatch, text, calls):
    ctx = types.SimpleNamespace(get_context=lambda m, **kw: (calls.append(kw), {"text": text, "trace": {"sections": {
        "records": {"refs": ["r1"]}, "knowledge": {"refs": ["k1"]}}}})[1])
    monkeypatch.setitem(sys.modules, "walter_memory.context", ctx)
    import walter_memory
    monkeypatch.setattr(walter_memory, "context", ctx, raising=False)


def test_chronological_only_for_a_light_plan_about_what_just_happened():
    assert retrieval.chronological(plan()) == 24
    assert retrieval.chronological(plan(horizons=("day",))) == 48
    assert retrieval.chronological(plan(level="L3")) is None                       # a heavy plan keeps its memory
    assert retrieval.chronological(plan(personal=("preferences",))) is None
    assert retrieval.chronological(plan(horizons=("long",))) is None
    assert retrieval.chronological(plan(observations={"people": [{"text": "Paul"}]})) is None   # their card
    assert retrieval.chronological(plan(observations={"dates": [{"text": "hier"}]})) is None    # the period
    budget = retrieval._memory_budget(plan())
    assert budget["evidence"] > 0 and not any(budget[k] for k in ("records", "knowledge", "views", "people"))


def test_records_are_their_own_block_and_go_before_the_tool_card(monkeypatch):
    calls = []
    text = ("## Décisions et règles consignées (texte en vigueur, daté)\n" + "- [2026-10-04] règle sans rapport\n" * 80
            + "\n## Mémoire pertinente\n- fait utile (2026-11-27)")
    fake_memory(monkeypatch, text, calls)
    blocks = retrieval.memory(plan(personal=()), "question")
    assert [b.id for b in blocks] == ["memory", "records"]
    assert "fait utile" in blocks[0].text and "règle sans rapport" not in blocks[0].text
    card = retrieval.Block("tool_cards", 4, "### memory\n" + "- `memory_events(order: newest|oldest)`\n" * 40)
    p = pack(plan(personal=()), [card, *blocks, retrieval.now()], budget=800)
    kept = {b.id: b.tokens for b in p.per_message()}
    assert kept.get("tool_cards") == card.tokens and "fait utile" in p.text()       # the intent's information stays
    assert p.cuts[0]["block"] == "records"                                         # historic records go first
    assert p.summary()["tokens_per_message"] <= 800


def test_the_early_rerank_waits_for_the_plan_and_is_skipped_when_not_taken(monkeypatch):
    asked = []

    def get_context(message, *, budget, include_profile, before_rerank=None, **kw):
        asked.append(before_rerank())               # Memory asks the gate once its candidates are found
        return {"text": "## Mémoire pertinente\n- x", "trace": {"sections": {}}}
    fake = types.SimpleNamespace(get_context=get_context)
    monkeypatch.setitem(sys.modules, "walter_memory.context", fake)
    import walter_memory
    monkeypatch.setattr(walter_memory, "context", fake, raising=False)
    monkeypatch.setattr(retrieval, "session_state", lambda *a, **k: None)
    monkeypatch.setattr(retrieval, "_notes", lambda ttl=600: [])
    pre = retrieval.Prefetch("mes derniers messages", None)
    time.sleep(0.1)
    assert not asked                                 # still waiting: no plan yet
    assert "memory" not in pre.taken(plan(), "mes derniers messages", None)
    pre.memory.result(timeout=2)
    assert asked == [False]                          # a chronological plan: no rerank
    heavy = plan(level="L3", personal=())
    pre2 = retrieval.Prefetch("où en est Sagora", None)
    assert "memory" in pre2.taken(heavy, "où en est Sagora", None)
    pre2.memory.result(timeout=2)
    assert asked[-1] is True                         # the plan takes it: the rerank is made
