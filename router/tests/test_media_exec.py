from __future__ import annotations

import pytest

from walter_router import db, media_exec


def test_parameters_are_coerced_to_what_the_model_accepts():
    assert media_exec.coerce("minimax-h3/text-to-video", {"prompt": "x", "duration": 20, "resolution": "1080p",
                                                          "aspect_ratio": "16:9", "foo": 1}) == \
        {"prompt": "x", "duration": 15, "resolution": "768P", "aspect_ratio": "16:9"}
    assert media_exec.coerce("bytedance/seedance-2-5", {"prompt": "x", "resolution": "4K"})["resolution"] == "1080p"
    assert media_exec.coerce("google/gemini-omni-flash-1-1", {"prompt": "x", "duration": 9})["duration"] in ("8", "10")


@pytest.fixture
def conn():
    with db.connect() as c:
        yield c
        c.rollback()


def test_kie_first_unless_clearly_dearer_and_openrouter_down_goes_last(conn):
    conn.execute("""insert into models.provider_status (provider, ok, detail) values ('openrouter', true, 't')
                    on conflict (provider) do update set ok = true""")
    # Seedance 2.5: OpenRouter is ~30 % cheaper than Kie at 720p -> OpenRouter first
    assert media_exec.choose_provider(conn, "seedance-2-5", "video", "720p", True, "bytedance/seedance-2.5")[0] == "openrouter"
    conn.execute("update models.provider_status set ok = false where provider = 'openrouter'")
    assert media_exec.choose_provider(conn, "seedance-2-5", "video", "720p", True, "bytedance/seedance-2.5")[0] == "kie"
    # H3: Kie is cheaper -> Kie first
    assert media_exec.choose_provider(conn, "minimax-h3", "video", "768p", True, "minimax/hailuo-3")[0] == "kie"


def test_ui_only_role_is_not_paid_silently(conn):
    out = media_exec.generate(conn, "témoignage face caméra TikTok", task="text_to_video", role="ugc", craft=False)
    assert out["mode"] == "manual_ui" and out["model_id"] == "gemini-omni-flash-1-1"
