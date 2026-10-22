from __future__ import annotations

import pytest

from walter_router.store import db
from walter_router.serve import media_exec


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


def test_fallback_and_kie_health():
    """2026-10-22: the fallback is the same model on its next provider; another model only when the owner declared
    one (the computed list stays available for the dossier). A provider seen down by the probe goes last."""
    from walter_router.store import db
    with db.connect() as conn:
        if not conn.execute("select 1 from models.preferences where task = 'text_to_video' limit 1").fetchone():
            return
        assert media_exec.fallback_models(conn, "text_to_video", "action", "minimax-h3", "t2v") == []   # none declared
        fb = media_exec.fallback_models(conn, "text_to_video", "action", "minimax-h3", "t2v", declared_only=False)
        assert fb and "minimax-h3" not in fb and all(m in media_exec._models() for m in fb)
        or_id = media_exec.openrouter_id(conn, "minimax-h3")
        conn.execute("update models.provider_status set ok = false where provider = 'kie'")
        assert media_exec.choose_provider(conn, "minimax-h3", "video", None, True, or_id)[0] == "openrouter"
        conn.rollback()
