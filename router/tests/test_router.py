from __future__ import annotations

import pytest

from walter_router.analysis import alerts
from walter_router.analysis import telegram
from walter_router.serve import choose
from walter_router.store import db
from walter_router.analysis import identity
from walter_router.analysis import select as sel


@pytest.mark.parametrize("ns,key,name,expected", [
    ("aa", "gpt-6-1-sol-high", "GPT-6.1 Sol (high)", ("gpt-6-1-sol", "high")),
    ("aa", "claude-opus-5-5", "Claude Opus 5.5 (max with fallback)", ("claude-opus-5-5", "max")),
    ("da", "gpt-6-astra-max", None, ("gpt-6-astra", "max")),
    ("mm", "GPT Image 2.5 Sunburst (max)", None, ("gpt-image-2-5-sunburst", "max")),
    ("mm", "MiniMax H3 Max (based on MiniMax H3)", None, ("minimax-h3-max", "")),
    ("mm", "Nano Banana 2 (Gemini 3.1 Flash Image)", None, ("nano-banana-2", "")),
    ("openrouter", "openai/gpt-6.1-sol", None, ("gpt-6-1-sol", "")),
    ("openrouter", "minimax/hailuo-3-max", None, ("minimax-h3-max", "")),
    ("kie", "Google nano banana 2", None, ("nano-banana-2", "")),
    ("kie", "wan 3.0 video", None, ("wan-3", "")),
    ("openrouter", "bytedance/seedance-2.0", None, ("seedance-2", "")),
    ("arena", "gemini-omni-1.1-flash", None, ("gemini-omni-flash-1-1", "")),
    ("arena", "dreamina-seedance-2.5-720p", None, ("seedance-2-5", "720p")),
    ("arena", "veo-3.1-fast-audio-1080p", None, ("veo-3-1-fast", "audio-1080p")),
    ("arena", "claude-opus-5.5-max", None, ("claude-opus-5-5", "max")),
    ("arena", "flux-3-video-20260811", None, ("flux-3-video", "")),
    ("aa", "qwen3-0-6b", "Qwen3 0.6B", ("qwen-3-0-6b", "")),
    ("codex", "gpt-6.1-sol", None, ("gpt-6-1-sol", "")),
])
def test_identity_is_deterministic(ns, key, name, expected):
    assert identity.normalize(ns, key, name) == expected


def _offer(provider, access="paid", pin=None, pout=None, interface="chat", unit_price=None, unit=None):
    return dict(provider=provider, offer_key=f"{provider}-x", access=access, interface=interface,
                price_in_1m=pin, price_out_1m=pout, unit_price=unit_price, unit=unit)


def test_chat_route_scales_list_cost_by_provider_ratio_and_keeps_subscription():
    offers = [_offer("openrouter", pin=2, pout=10), _offer("kie", pin=0.6, pout=3), _offer("codex", access="subscription")]
    route = sel.chat_route(offers, 1.0)
    assert route["subscription"] == "codex"
    assert route["paid"]["provider"] == "kie"
    assert route["paid"]["cost"] == pytest.approx(0.3)


def test_chat_route_without_list_reference_is_unscaled():
    route = sel.chat_route([_offer("kie", pin=0.6, pout=3)], 1.0)
    assert route["paid"]["cost"] == 1.0 and route["paid"]["basis"] == "unscaled_no_list_reference"


def test_media_route_only_compares_the_task_unit():
    offers = [_offer("kie", interface="image", unit_price=0.03, unit="per image"),
              _offer("kie", interface="image", unit_price=0.002, unit="per request")]
    assert sel.media_route(offers, "image")["paid"]["cost"] == 0.03


@pytest.fixture
def conn():
    with db.connect() as c:
        if c.execute("select to_regclass('models.latest_run') as t").fetchone()["t"] is None:
            pytest.skip("schema not migrated")
        if choose.latest_run(c) is None:
            pytest.skip("no refresh yet")
        yield c
        c.rollback()  # every test below leaves the real database untouched


def test_pinned_favourite_wins_over_computed_choice(conn):
    choose.set_preference(conn, "3d", pin="claude-opus-5-5", note="test")
    got = choose.pick(conn, "3d")
    assert got["source"] == "preference_pinned" and got["model_id"] == "claude-opus-5-5"


def test_challenger_flow_baseline_then_new_then_adopt(conn):
    # Pin a weaker model: everything already better (on the task composite) becomes 'baseline' (no message).
    out = choose.set_preference(conn, "3d", pin="claude-opus-5")
    assert out["baseline_challengers"] > 0
    assert not [a for a in alerts.pending(conn) if a["kind"] == "challenger" and a["task"] == "3d"]
    # A model overtaking later is 'open' and gets rendered for Telegram.
    conn.execute("delete from models.alerts where kind = 'challenger' and task = '3d' and subject = 'gpt-6-astra'")
    # an UNCHANGED better model is not news; a new (or cheaper) one is
    still = {"new": {}, "nerf": {}, "price_drop": {}}
    assert alerts.challengers(conn, "open", only_task="3d", chg=still) == []
    conn.execute("delete from models.alerts where kind = 'challenger' and task = '3d' and subject = 'gpt-6-astra'")
    news = {"new": {"gpt-6-astra": ["nouveau sur da_models:3d"]}, "nerf": {}, "price_drop": {}}
    assert "3d:default:gpt-6-astra" in alerts.challengers(conn, "open", only_task="3d", chg=news)
    pend = [a for a in alerts.pending(conn) if a["task"] == "3d"]
    assert pend and "Catégorie du router" in telegram.render(pend, conn)
    assert pend[0]["evidence"]["composite"]["challenger"] > pend[0]["evidence"]["composite"]["pinned"]
    # The owner adopts it: it becomes the pinned favourite.
    alerts.verdict(conn, pend[0]["alert_id"], "adopted")
    assert choose.pick(conn, "3d")["model_id"] == "gpt-6-astra"


def test_best_available_objective_without_pin_takes_top_callable(conn):
    choose.set_preference(conn, "text_to_video", objective="best_available")  # no pin, rolled back
    got = choose.pick(conn, "text_to_video")
    best = conn.execute("""select max(quality) as q from models.selection where run_id = %s and task = 'text_to_video'
                           and level = 'best'""", (choose.latest_run(conn),)).fetchone()["q"]
    assert got["objective"] == "best_available" and got["quality"] == best


def test_image_favourite_is_sunburst(conn):
    assert choose.pick(conn, "text_to_image")["model_id"] == "gpt-image-2-5-sunburst"


def test_tool_tasks_never_get_a_model(conn):
    assert choose.pick(conn, "weather")["mode"] == "tool"


def test_per_video_price_with_duration_becomes_per_second():
    offers = [_offer("kie", interface="video", unit_price=0.63, unit="per video")]
    offers[0]["offer_key"] = "google/gemini-omni-flash-1-1, video, 10s 720p no video input"
    assert sel.media_route(offers, "video")["paid"]["cost"] == pytest.approx(0.063)
    offers[0]["offer_key"] = "kling 2.6, text-to-video, with audio-10.0s"
    assert sel.media_route(offers, "video")["paid"]["cost"] == pytest.approx(0.063)


def test_roles_keep_separate_favourites(conn):
    choose.set_preference(conn, "text_to_video", pin="seedance-2-5", note="top")
    choose.set_preference(conn, "text_to_video", pin="minimax-h3", role="action", watch="dominance")
    assert choose.pick(conn, "text_to_video")["model_id"] == "seedance-2-5"
    got = choose.pick(conn, "text_to_video", role="action")
    assert got["model_id"] == "minimax-h3" and "default" in got["other_roles"]


def test_dominance_watch_ignores_better_but_dearer_models(conn):
    # Budget favourite: a better model only counts if it is no more expensive per second.
    choose.set_preference(conn, "image_to_video", pin="grok-imagine-video-1-5", role="budget", watch="dominance")
    conn.execute("delete from models.alerts where task = 'image_to_video' and role = 'budget'")
    alerts.challengers(conn, "open", only_task="image_to_video", only_role="budget")
    for a in conn.execute("""select evidence from models.alerts where task = 'image_to_video' and role = 'budget'
                             and kind = 'challenger' and subject not like '%%:unmeasured'"""):
        e = a["evidence"]
        assert e["unit_cost"] <= e["pinned_unit_cost"] and e["score"] > e["pinned_score"]


def test_notification_buttons_one_row_per_news():
    from walter_router.analysis import alerts
    rows = telegram.keyboard(None, [{"alert_id": 1, "kind": "tier", "ref": 3, "role": "L2", "subject": "gpt-6-luna/max",
                                   "evidence": {"current": "gpt-6-1-sol/medium"}},
                                  {"alert_id": 2, "kind": "nerf", "ref": 4, "role": "", "subject": "minimax-h3"}])
    assert [[b["callback_data"] for b in r] for r in rows] == [["wr:a:3", "wr:d:3"], ["wr:d:4"]]
    assert all(len(b["callback_data"]) <= 64 for r in rows for b in r)
    assert rows[0][0]["text"] == "✅ Passer à gpt-6-luna" and rows[0][1]["text"] == "✖️ Garder gpt-6-1-sol"


def test_one_board_is_not_enough(conn):
    """2026-10-14: Grok Imagine 1.5 led one board (Arena t2v, 'agent' version) but MiniMax H3 is far ahead on the
    composite: no challenger alert against H3."""
    choose.set_preference(conn, "text_to_video", pin="minimax-h3", role="action", watch="dominance")
    conn.execute("delete from models.alerts where kind = 'challenger' and task = 'text_to_video'")
    news = {"new": {"grok-imagine-video-1-5": ["nouveau chez kie"]}, "nerf": {}, "price_drop": {}}
    made = alerts.challengers(conn, "open", only_task="text_to_video", only_role="action", chg=news)
    assert "text_to_video:action:grok-imagine-video-1-5" not in made


def test_successor_family_and_runnable_selection(conn):
    """2026-10-14: the chosen model of a media task must be runnable (logo: GPT Image 2 measured first but not wired)."""
    from walter_router.analysis import select as sel
    from walter_router.serve import media_exec
    assert sel.family("gpt-image-2-5-sunburst") == ("gpt-image", (2, 5), "sunburst")
    assert sel.family("gpt-image-2")[1] < sel.family("gpt-image-2-5-flare")[1]
    assert sel.same_line("gpt-image-2", "gpt-image-2-5-sunburst")
    assert not sel.same_line("gemini-3-1-flash-live-high", "gemini-3-8-flash-tts")   # 2026-10-18: TTS is not a Live
    assert sel.same_line("gemini-3-1-flash-live-high", "gemini-3-8-flash-live")
    assert not sel.same_line("gpt-image-2-5", "gpt-image-2")
    best = conn.execute("""select model_id from models.selection where run_id = (select run_id from models.latest_run)
                           and task = 'logo' and level = 'best' and rank = 1""").fetchone()
    assert best and best["model_id"] in media_exec._models()


def test_level_poste_follows_the_owners_text_tier(conn):
    """Background postes (2026-10-16) take the 'general' tier the owner adopted, never a model of their own."""
    tier = choose.pick(conn, "general", level="L1")
    for poste in ("summarization", "memory_extraction"):
        d = choose.pick(conn, poste)
        assert d["model_id"] == tier["model_id"] and d["variant"] == tier["variant"]
        assert d["follows"] == {"task": "general", "level": "L1"} and d["task"] == poste


def test_internal_postes_are_not_offered_to_the_intent_classifier(conn):
    from walter_router.serve import intent
    tasks, _ = intent._criteria(conn)
    assert not {"summarization", "memory_extraction", "voice_assist", "stt", "embeddings", "rerank"} & set(tasks)


def test_unranked_successor_is_saved_and_proposed(conn):
    """A newer version leading a media task before its board ranks it has no score (2026-10-19 refresh failure)."""
    task = conn.execute("select task from models.tasks where interface <> 'chat' and task <> 'general' limit 1").fetchone()["task"]
    model = conn.execute("select model_id from models.canonical limit 1").fetchone()["model_id"]
    run = conn.execute("insert into models.runs (status) values ('ok') returning run_id").fetchone()["run_id"]
    sel.save(conn, run, [{"task": task, "level": "best", "rank": 1, "model_id": model, "variant": "", "display_name": model,
                          "quality": None, "quality_unit": "Composite /100", "real_cost": None, "cost_unit": None,
                          "provider": None, "offer_key": None, "subscription": None,
                          "reasons": {"warning": "version supérieure", "measured_quality": 80.0}}])
    row = conn.execute("select quality, reasons from models.selection where run_id = %s", (run,)).fetchone()
    assert row["quality"] is None and row["reasons"]["measured_quality"] == 80.0
    lines = telegram._block(conn, {"kind": "new_best", "subject": model, "task": task, "ref": "t1",
                                 "evidence": {"previous_name": "Ancien", "score": None, "previous_score": 80.0, "why": []}})
    assert any("pas encore classée" in line for line in lines if line)


def test_cli_classify_and_decision_chain_parse():
    """2026-10-21: a local `from . import intent` in main() made `classify` raise UnboundLocalError."""
    import ast, inspect
    from walter_router import cli
    tree = ast.parse(inspect.getsource(cli.main))
    local = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and any(a.name == "intent" for a in n.names)]
    assert not local
