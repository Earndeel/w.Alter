"""2026-10-22: the video-input constraint and what an agent gets from `route`."""
from __future__ import annotations

import io
import json


from walter_router.analysis import select as sel
from walter_router.serve import agent_view, brief, choose, intent, routes
from walter_router.store import db

def test_a_route_needing_video_only_counts_offers_that_read_video():
    offers = [dict(provider="codex", offer_key="x", access="subscription", interface="chat", price_in_1m=None,
                   price_out_1m=None, modes=[]),
              dict(provider="kie", offer_key="y", access="paid", interface="chat", price_in_1m=1, price_out_1m=4, modes=[]),
              dict(provider="openrouter", offer_key="z", access="paid", interface="chat", price_in_1m=2, price_out_1m=8,
                   modes=["image", "video"])]
    route = sel.chat_route(offers, None, ["video"])
    assert route["callable"] and route["paid"]["provider"] == "openrouter" and route["subscription"] is None
    assert not sel.chat_route(offers[:2], None, ["video"])["callable"]
    assert sel.chat_route(offers, None)["subscription"] == "codex"   # other tasks: unchanged


def test_video_input_constraint_picks_a_model_that_reads_video_on_a_route_that_reads_it():
    """No video category (owner, 2026-10-22: no satisfying benchmark); analysing a video = an image-analysis task
    with the hard constraint video_input, and every execution route must read the video."""
    with db.connect() as conn:
        d = routes.with_execution(conn, choose.pick(conn, "vision", require="video_input"))
        if d.get("mode") == "delegate":
            offers = sel.load_offers(conn, sel.latest_snapshots(conn))[d["model_id"]]
            assert any("video" in (o["modes"] or []) for o in offers)
            assert d["execution"] and all(r["hermes_provider"] == "openrouter" for r in d["execution"])
        conn.rollback()


def test_route_does_not_ask_the_decision_model_what_the_caller_fixed(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("decision model called")
    monkeypatch.setattr(intent, "classify", refuse)
    with db.connect() as conn:
        out = routes.route(conn, "planifie le tournage", task="general", level="L2")
        assert out["intent"] == {"skipped": "task and level given by the caller"} and out["level"] == "L2"
        conn.rollback()


def test_route_passes_the_conversation_to_the_decision_model(monkeypatch):
    seen = {}

    def fake(conn, request, context=None, **k):
        seen.update(request=request, context=context)
        return {"task": "general", "task_confidence": 0.9, "level": "L1", "unrestricted": False}
    monkeypatch.setattr(intent, "classify", fake)
    with db.connect() as conn:
        routes.route(conn, "fais la suite", context="analyse d'une vidéo de référence client")
        assert seen == {"request": "fais la suite", "context": "analyse d'une vidéo de référence client"}
        conn.rollback()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_classify_sends_the_context_in_the_state(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent.update(json.loads(req.data))
        answers = {name: {"choice": next(iter(q["criteria"])), "confidence": 0.9,
                          "probabilities": {next(iter(q["criteria"])): 0.9}} for name, q in sent["questions"].items()}
        return _Resp(json.dumps({"model": "typesafe/jev-1.13-x", "answers": answers}).encode())
    monkeypatch.setattr(intent, "urlopen", fake_urlopen)
    monkeypatch.setattr(intent.instance, "env_value", lambda name: "k")
    with db.connect() as conn:
        intent.classify(conn, "pareil en mieux", models=(intent.MODEL,), context="logo d'une boulangerie")
        conn.rollback()
    assert sent["state"] == {"request": "pareil en mieux", "context": "logo d'une boulangerie"}
    assert "context" in sent["questions"]["task"]["instructions"]


def test_agent_sees_route_prices_and_no_media_route_for_text():
    d = {"task": "general", "model_id": "gpt-6-1-sol", "route": {"paid": {"provider": "kie", "offer_key": "x"}},
         "execution": [{"hermes_provider": "openai-codex", "model": "gpt-6.1-sol", "reasoning": "medium",
                        "cost_price_1m": {"in": 0.0411, "out": 0.2056},
                        "subscription": {"plan": "ChatGPT Plus", "quota_used_percent": 5.0, "cost_ratio": 0.02}},
                       {"hermes_provider": "openrouter", "model": "openai/gpt-6.1-sol", "blended_1m": 3.1,
                        "host": {"host": "OpenAI", "price_in_1m": 1.25, "price_out_1m": 10.0}}]}
    out = agent_view.view(d)
    assert "media_route" not in out
    assert out["execution"][0]["usd_per_1m"] == {"in": 0.0411, "out": 0.2056}
    assert out["execution"][0]["subscription"] == {"plan": "ChatGPT Plus", "quota_used_percent": 5.0}
    assert out["execution"][1]["usd_per_1m"] == {"in": 1.25, "out": 10.0} and out["execution"][1]["host"] == "OpenAI"


def test_brief_names_no_model_and_fits_a_system_prompt_section():
    """2026-10-22 (owner): the agent must know the router exists, what it is for and its parameters (specialities,
    levels, generation, analysis, constraints) without model or provider names."""
    with db.connect() as conn:
        text = brief.text(conn)
        names = {r["model_id"] for r in conn.execute(
            "select distinct pinned_model_id as model_id from models.preferences where pinned_model_id is not null")}
        conn.rollback()
    assert len(text) <= brief.MAX_CHARS
    for word in ("walter_route", "walter_run", "walter_generate", "walter_plans", "L1", "L2", "L3", "`vision`",
                 "`text_to_video`", "`premium`", "`video_input`"):
        assert word in text
    assert not [m for m in names if m in text]
    for provider in ("OpenRouter", "Kie", "Codex", "Flow"):
        assert provider not in text


def test_brief_file_is_rewritten_only_when_it_changed():
    with db.connect() as conn:
        assert brief.write(conn) is True and brief.write(conn) is False
        conn.rollback()
