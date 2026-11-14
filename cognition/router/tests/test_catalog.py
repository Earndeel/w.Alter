from __future__ import annotations

import pytest

from walter_router.analysis import alerts
from walter_router.analysis import telegram
from walter_router.analysis import catalog
from walter_router.analysis import parse
from walter_router.research.benchmarks import arena
from walter_router.store import db
from walter_router.analysis import media


@pytest.mark.parametrize("interface,label,inputs,kind,modes", [
    ("video", "kling 2.6, text-to-video, with audio-10.0s".split(", ", 1)[1], None, "generation", ["t2v"]),
    ("video", "Text /Image to Video, 360p（no audio）", None, "generation", ["t2v", "i2v"]),
    ("video", "video, 720p with video input", None, "generation", ["v2v"]),
    ("video", "video, 10s 720p no video input", None, "generation", ["t2v", "i2v"]),
    ("video", "Reference-to-Video Output | 480p", None, "generation", ["r2v"]),
    ("video", "Video Output | 768p", ["text", "image"], "generation", ["t2v", "i2v"]),
    ("video", "Image Input", ["text", "image"], "fee", []),
    ("video", "Extend, 1080p(with aiduo)", None, "tool", []),
    ("video", "Video Upscale Output", None, "tool", []),
    ("image", "image-to-image, 2K", None, "generation", ["i2i"]),
    ("image", "Image Output | 4K", ["text", "image"], "generation", ["t2i", "i2i"]),
    ("image", "Web Search", ["text"], "fee", []),
])
def test_classify_offer(interface, label, inputs, kind, modes):
    c = media.classify(interface, label, inputs)
    assert c["kind"] == kind and sorted(c["modes"]) == sorted(modes)


def test_resolution_and_price_normalisation():
    assert media.resolution("Image Output | 768", "768") == "768p"
    assert media.resolution("seedream 5 Flash, Image to image, 1.5K") == "1.5K"
    assert media.norm_price("video", 0.63, "per video", "10s 720p") == (pytest.approx(0.063), "per second")
    assert media.norm_price("audio", 0.000022, "per character", "Characters") == (pytest.approx(0.022), "per 1000 characters")
    assert media.norm_price("image", 0.002, "per request", "x") == (None, "per request")


def test_task_modes_restrict_pricing():
    assert media.compatible(["i2i"], ["i2i"]) and not media.compatible(["t2i"], ["i2i"])
    assert media.compatible([], ["t2v"]) and not media.compatible([], ["v2v"])


def test_one_line_per_model_with_prices_per_resolution():
    c = {"name": "FLUX.3 Image", "interface": "image", "modes": ["t2i", "i2i"], "providers": ["openrouter"], "audio": [],
         "prices": {"1K": {"price": 0.03, "unit": "per image", "provider": "openrouter"},
                    "4K": {"price": 0.12, "unit": "per image", "provider": "openrouter"}}}
    line = catalog.line(c)
    assert line == "🖼️ FLUX.3 Image — t2i/i2i — 1K 0,03 · 4K 0,12 $/img — OpenRouter" and "\n" not in line


def test_many_resolutions_collapse_to_a_range():
    prices = {r: {"price": p, "unit": "per second", "provider": "kie"}
              for r, p in (("480p", 0.1), ("720p", 0.2), ("1080p", 0.4), ("2K", 0.6), ("4K", 1.2))}
    c = {"name": "X", "modes": ["t2v"], "providers": ["kie"], "audio": [False, True], "prices": prices}
    assert catalog.price_text(c) == "0,1–1,2 $/s (480p→4K) (son en option)"


def test_arena_board_is_read_from_page_flight_data():
    page = ('<script>self.__next_f.push([1,"x\\"id\\":\\"leaderboard-sets/public/leaderboards/text_to_video-overall-raw'
            '/leaderboard-snapshots/latest\\",\\"entries\\":[{\\"rank\\":1,\\"modelDisplayName\\":\\"gemini-omni-1.1-flash'
            '\\",\\"rating\\":1516.2,\\"ratingLower\\":1500.7,\\"ratingUpper\\":1531.6,\\"votes\\":1784}]"])</script>')
    board = arena.arena_board(page)
    assert board["rows"][0]["modelDisplayName"] == "gemini-omni-1.1-flash"
    rows = parse.parse_benchmarks("arena", {"boards": {"text_to_video": board}})
    assert rows[0]["model_id"] == "gemini-omni-flash-1-1" and rows[0]["score"] == pytest.approx(1516.2)


@pytest.fixture
def conn():
    with db.connect() as c:
        if c.execute("select to_regclass('models.catalog') as t").fetchone()["t"] is None:
            pytest.skip("schema 004 not migrated")
        yield c
        c.rollback()


def test_unranked_alert_is_one_per_model(conn):
    conn.execute("delete from models.alerts where kind = 'unranked'")
    alerts.unranked(conn)
    rows = conn.execute("select * from models.alerts where kind = 'unranked'").fetchall()
    assert rows and all("|" not in r["subject"] for r in rows)


def test_favourite_is_checked_on_every_board_of_the_task(conn):
    boards = {r["benchmark"] for r in conn.execute(
        "select benchmark from models.task_benchmarks where task = 'text_to_video'")}
    assert boards == {"aa_mm", "arena"}
    conn.execute("delete from models.alerts where task = 'text_to_video' and role = 'default'")
    alerts.challengers(conn, "open", only_task="text_to_video", only_role="default")
    ev = [r["evidence"] for r in conn.execute("""select evidence from models.alerts where task = 'text_to_video'
                                                 and role = 'default' and kind = 'challenger'
                                                 and subject not like '%%:unmeasured'""")]
    assert any(any(b.startswith("Arena") for b in e["boards"]) for e in ev)


def test_video_editor_is_not_text_to_video():
    assert media.classify("video", "", ["text", "video"])["modes"] == ["v2v"]
    assert sorted(media.classify("video", "", ["text", "image", "video", "audio"])["modes"]) == ["i2v", "t2v", "v2v"]


def test_music_side_operations_are_not_song_prices():
    assert media.classify("music", "Generate Lyrics")["kind"] == "tool"
    assert media.classify("music", "Generate Music")["kind"] == "generation"


def test_unrestricted_finetune_points_to_its_base_model():
    from walter_router.analysis import identity
    assert identity.policy("glm-5-3-flash-uncensored") == ("unrestricted", "glm-5-3-flash")
    assert identity.policy("gpt-6-1-sol") == ("standard", None)
    assert identity.normalize("hermes_providers", "zai/glm-5.3-flash-uncensored/flex") == ("glm-5-3-flash-uncensored", "")


def test_icons_show_the_kind_of_model():
    c = {"name": "X", "interface": "video", "modes": [], "providers": [], "prices": {}, "audio": [],
         "content_policy": "unrestricted"}
    assert catalog.line(c).startswith("🎬 🔓 X")


def test_unranked_releases_are_never_sent(conn):
    conn.execute("""insert into models.alerts (kind, task, subject, evidence, status)
                    values ('unranked', 'image', 'zz-test-model', '{}', 'open')""")
    assert not [a for a in alerts.pending(conn) if a["kind"] == "unranked"]


def test_new_best_for_a_specialised_task_is_the_only_kind_of_news(conn):
    from walter_router.serve import choose
    prev = choose.latest_run(conn)
    old = conn.execute("""select model_id from models.selection where run_id = %s and task = 'coding' and level = 'best'
                          and rank = 1""", (prev,)).fetchone()["model_id"]
    new_run = conn.execute("insert into models.runs (status) values ('ok') returning run_id").fetchone()["run_id"]
    for mid, q, rank in (("zz-newcomer", 99.0, 1), (old, 80.0, 2)):
        conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (mid,))
        conn.execute("""insert into models.selection (run_id, task, level, rank, model_id, display_name, quality)
                        values (%s, 'coding', 'best', %s, %s, %s, %s)""", (new_run, rank, mid, mid, q))
    conn.execute("delete from models.preferences where task = 'coding'")
    assert alerts.new_best(conn, new_run, {"new": {}, "nerf": {}, "price_drop": {}}) == []  # unchanged: silent
    # …but never a silent switch (2026-10-16): the model in use is pinned until the owner decides
    assert conn.execute("select pinned_model_id from models.preferences where task = 'coding'").fetchone()[
        "pinned_model_id"] == old
    conn.execute("delete from models.preferences where task = 'coding'")
    conn.execute("delete from models.alerts where kind = 'new_best' and subject = 'zz-newcomer'")
    news = {"new": {"zz-newcomer": ["nouveau sur arena:text_coding"]}, "nerf": {}, "price_drop": {}}
    assert alerts.new_best(conn, new_run, news) == ["coding:zz-newcomer"]
    pend = alerts.pending(conn)
    # live alerts of the other kinds may be pending in the real catalog (pareto, nerf, plan changes, outages)
    assert {a["kind"] for a in pend} - {"board_down", "pareto", "nerf", "plan_change"} <= {"challenger", "tier", "new_best"}
    a = next(a for a in pend if a["kind"] == "new_best" and a.get("subject") == "zz-newcomer")   # not a live one
    assert "proposé" in telegram.render([a], conn)
    assert conn.execute("select pinned_model_id from models.preferences where task = 'coding'").fetchone()[
        "pinned_model_id"] == old                       # proposed, not switched
    alerts.verdict(conn, a["alert_id"], "adopted")      # « Passer au nouveau » pins the newcomer
    assert conn.execute("select pinned_model_id from models.preferences where task = 'coding'").fetchone()[
        "pinned_model_id"] == "zz-newcomer"


def test_unrestricted_pick_uses_an_unrestricted_model(conn):
    from walter_router.serve import choose
    got = choose.pick(conn, "general", require="unrestricted")
    if got["mode"] == "none":
        pytest.skip("no unrestricted provider collected")
    assert conn.execute("select content_policy from models.canonical where model_id = %s",
                        (got["model_id"],)).fetchone()["content_policy"] == "unrestricted"
