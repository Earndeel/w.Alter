"""2026-10-22: video understanding (boards, required video input) and what an agent gets from `route`."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path


from walter_router.analysis import parse, scoring
from walter_router.analysis import select as sel
from walter_router.research.benchmarks import video_evals
from walter_router.serve import intent, routes
from walter_router.store import db

VIDEO_MME_V2_PAGE = """<script>
    const leaderboardDataRaw = [
        { name: "Human Expert", logo: "human", type: "human", frames: "-", overall: [90.6786, null], avg_acc: [94.94, null] },
        { name: "Gemini-3-Pro", logo: "gemini", type: "proprietary", omni: true, frames: "1fps", level1: [1, 2], overall: [49.43, 38.2], avg_acc: [66.06, 56.84] },
        { name: "Qwen3.5-397B-A17B-Think", logo: "qwen", type: "open", frames: "512", overall: [39.1, 30.3], avg_acc: [55.9, null], stale: true },
    ];
</script>"""


def _llm_stats_page(models: list[dict]) -> str:
    data = {"benchmark_id": "lvbench", "name": "LVBench", "updated_at": "2026-10-21T20:05:06+00:00",
            "statistics": {"total_models": len(models), "verified_count": 0, "self_reported_count": len(models)},
            "models": models}
    flight = '2d:["$","$L2f",null,{"params":{"id":"lvbench"},"initialBenchmarkData":' + json.dumps(data) + "}]\n"
    return f"<script>self.__next_f.push([1,{json.dumps(flight)}])</script>"


def test_video_mme_v2_rows_skip_the_human_reference():
    rows = video_evals.video_mme_v2_rows(VIDEO_MME_V2_PAGE)
    assert [r["name"] for r in rows] == ["Gemini-3-Pro", "Qwen3.5-397B-A17B-Think"]
    assert rows[0]["overall"] == [49.43, 38.2] and rows[1]["stale"] and rows[1]["frames"] == "512"


def test_llm_stats_board_and_rows_are_flagged_self_reported():
    page = _llm_stats_page([{"model_id": "gemini-4-argon", "model_name": "Gemini 4 Argon", "score": 0.917,
                             "self_reported": True, "verified": False, "organization_name": "Google"}])
    board = video_evals.llm_stats_board(page)
    assert board["name"] == "LVBench" and board["models"][0]["score"] == 0.917
    doc = {"video_mme_v2": {"rows": video_evals.video_mme_v2_rows(VIDEO_MME_V2_PAGE)}, "llm_stats": {"lvbench": board}}
    rows = parse.parse_benchmarks("video_evals", doc)
    lv = next(r for r in rows if r["benchmark"] == "llm_stats")
    assert lv["model_id"] == "gemini-4-argon" and lv["score"] == 91.7 and lv["extra"]["self_reported"]
    assert scoring._reliability(lv) == scoring.SELF_REPORTED
    v2 = [r for r in rows if r["benchmark"] == "video_mme_v2" and r["model_id"] == "gemini-3-pro"]
    assert {r["task"] for r in v2} == {"with_subtitles", "without_subtitles"} and scoring._reliability(v2[0]) == 1.0
    qwen = next(r for r in rows if r["display_name"].startswith("Qwen"))
    assert qwen["model_id"] == "qwen-3-5-397b-a17b"   # thinking mode is not a separate model


def test_a_task_needing_video_only_counts_offers_that_read_video():
    offers = [dict(provider="codex", offer_key="x", access="subscription", interface="chat", price_in_1m=None,
                   price_out_1m=None, modes=[]),
              dict(provider="kie", offer_key="y", access="paid", interface="chat", price_in_1m=1, price_out_1m=4, modes=[]),
              dict(provider="openrouter", offer_key="z", access="paid", interface="chat", price_in_1m=2, price_out_1m=8,
                   modes=["image", "video"])]
    route = sel.chat_route(offers, None, ["video"])
    assert route["callable"] and route["paid"]["provider"] == "openrouter" and route["subscription"] is None
    assert not sel.chat_route(offers[:2], None, ["video"])["callable"]
    assert sel.chat_route(offers, None)["subscription"] == "codex"   # other tasks: unchanged


def test_video_understanding_task_requires_video_input():
    with db.connect() as conn:
        t = conn.execute("select * from models.tasks where task = 'video_understanding'").fetchone()
        assert t and t["modes"] == ["video"] and t["interface"] == "chat"
        boards = {(r["benchmark"], r["bench_task"]) for r in conn.execute(
            "select * from models.task_benchmarks where task = 'video_understanding'")}
        assert ("video_mme_v2", "with_subtitles") in boards and ("llm_stats", "lvbench") in boards
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


def _plugin():
    path = Path(__file__).resolve().parent.parent / "hermes-plugins" / "walter-router" / "__init__.py"
    spec = importlib.util.spec_from_file_location("walter_router_plugin_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agent_sees_route_prices_and_no_media_route_for_text():
    plugin = _plugin()
    d = {"task": "general", "model_id": "gpt-6-1-sol", "route": {"paid": {"provider": "kie", "offer_key": "x"}},
         "execution": [{"hermes_provider": "openai-codex", "model": "gpt-6.1-sol", "reasoning": "medium",
                        "cost_price_1m": {"in": 0.0411, "out": 0.2056},
                        "subscription": {"plan": "ChatGPT Plus", "quota_used_percent": 5.0, "cost_ratio": 0.02}},
                       {"hermes_provider": "openrouter", "model": "openai/gpt-6.1-sol", "blended_1m": 3.1,
                        "host": {"host": "OpenAI", "price_in_1m": 1.25, "price_out_1m": 10.0}}]}
    out = plugin._compact(d)
    assert "media_route" not in out
    assert out["execution"][0]["usd_per_1m"] == {"in": 0.0411, "out": 0.2056}
    assert out["execution"][0]["subscription"] == {"plan": "ChatGPT Plus", "quota_used_percent": 5.0}
    assert out["execution"][1]["usd_per_1m"] == {"in": 1.25, "out": 10.0} and out["execution"][1]["host"] == "OpenAI"
    assert "Jev" not in plugin.ROUTE_SCHEMA["description"]
    assert "conversation" in plugin.ROUTE_SCHEMA["parameters"]["properties"]
