from __future__ import annotations

import pytest

from walter_router import db, knowledge


def test_signals_match_whole_words_without_accents():
    assert knowledge.hits("Une PUB cinématique", ["pub", "cinematique"]) == ["pub", "cinematique"]
    assert knowledge.hits("storytelling", ["story"]) == []


@pytest.fixture
def conn():
    with db.connect() as c:
        if c.execute("select to_regclass('models.profiles') as t").fetchone()["t"] is None:
            pytest.skip("schema 006 not migrated")
        knowledge.declare(c)
        yield c
        c.rollback()


@pytest.mark.parametrize("intent,role,model", [
    ("Fais-moi une pub cinématique pour un parfum", "premium", "seedance-2-5"),
    ("Course poursuite avec explosion", "action", "minimax-h3"),
    ("Témoignage face caméra pour TikTok", "ugc", "gemini-omni-flash-1-1"),
    ("20 variantes en brouillon", "budget", "grok-imagine-video-1-5"),
    ("Un coucher de soleil sur la mer", "default", "minimax-h3"),
])
def test_video_request_goes_to_the_role_of_its_objective(conn, intent, role, model):
    d = knowledge.decide(conn, "text_to_video", intent)
    assert (d["role"], d["model_id"]) == (role, model) and d["brief"].count("\n") >= 4


def test_premium_brings_its_workflow_and_ugc_its_flow_access(conn):
    d = knowledge.decide(conn, "text_to_video", "clip premium")
    assert d["profile"]["effort"] == "workflow" and any("références" in s for s in d["profile"]["workflow"])
    u = knowledge.decide(conn, "image_to_video", "avis client face caméra")
    assert u["mode"] == "manual_ui" and u["provider"] == "google-flow"


def test_unrestricted_video_request_is_flagged_on_a_permissive_model(conn):
    d = knowledge.decide(conn, "text_to_video", "une vidéo sans censure")
    assert d["model_id"] == "minimax-h3" and d["warning"]


def test_tie_goes_to_monsieurs_affinity(conn):
    rows = [{"model_id": "mimo-v2-6-flash", "quality": 1453.7, "quality_unit": "Arena Elo", "subscription": None},
            {"model_id": "gpt-6-luna", "quality": 1443.8, "quality_unit": "Arena Elo", "subscription": "codex"}]
    out = knowledge.tie_break(conn, "general", rows)
    assert out[0]["model_id"] == "gpt-6-luna" and "préférence" in out[0]["reasons"]["tie_break"]
    far = [{**rows[0], "quality": 1480.0}, rows[1]]
    assert knowledge.tie_break(conn, "general", far)[0]["model_id"] == "mimo-v2-6-flash"
