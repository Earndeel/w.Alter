from __future__ import annotations

import pytest

from walter_router import alerts, choose, db, identity
from walter_router import select as sel


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
    # Pin a weaker model: everything already better becomes 'baseline' (no message for those).
    out = choose.set_preference(conn, "3d", pin="claude-opus-5-5")
    assert out["baseline_challengers"] > 0
    assert not [a for a in alerts.pending(conn) if a["kind"] == "challenger" and a["task"] == "3d"]
    # A model overtaking later is 'open' and gets rendered for Telegram.
    conn.execute("delete from models.alerts where kind = 'challenger' and task = '3d' and subject = 'gpt-6-astra'")
    assert "3d:default:gpt-6-astra" in alerts.challengers(conn, "open", only_task="3d")
    pend = [a for a in alerts.pending(conn) if a["task"] == "3d"]
    assert pend and "dépasse" in alerts.render(pend, conn)
    # Monsieur adopts it: it becomes the pinned favourite.
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
