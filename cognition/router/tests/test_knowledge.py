from __future__ import annotations

import pytest

from walter_router.store import db
from walter_router.analysis import knowledge


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


@pytest.mark.parametrize("intent,role", [
    ("Fais-moi une pub cinématique pour un parfum", "premium"),
    ("Course poursuite avec explosion", "action"),
    ("Témoignage face caméra pour TikTok", "ugc"),
    ("20 variantes en brouillon", "budget"),
    ("Un coucher de soleil sur la mer", "default"),
])
def test_video_request_goes_to_the_role_of_its_objective(conn, intent, role):
    # the favourite of each role is the instance's (the owner moved budget from Grok to HeyGen on 2026-10-24/25),
    # not a model named here: the test checks that the request lands on its role and gets that role's model
    model = knowledge.load()["roles"][role]["model"]
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


def test_tie_goes_to_the_owners_affinity(conn):
    rows = [{"model_id": "mimo-v2-6-flash", "quality": 1453.7, "quality_unit": "Arena Elo", "subscription": None},
            {"model_id": "gpt-6-luna", "quality": 1443.8, "quality_unit": "Arena Elo", "subscription": "codex"}]
    out = knowledge.tie_break(conn, "general", rows)
    assert out[0]["model_id"] == "gpt-6-luna" and "préférence" in out[0]["reasons"]["tie_break"]
    far = [{**rows[0], "quality": 1480.0}, rows[1]]
    assert knowledge.tie_break(conn, "general", far)[0]["model_id"] == "mimo-v2-6-flash"


def test_tie_group_puts_subscription_first_but_not_beyond_the_margin(conn):
    rows = [{"model_id": "claude-opus-5-5", "quality": 86.4, "quality_unit": "Composite /100", "subscription": None},
            {"model_id": "claude-fable-5-1", "quality": 86.3, "quality_unit": "Composite /100", "subscription": None},
            {"model_id": "gpt-6-astra", "quality": 85.7, "quality_unit": "Composite /100", "subscription": "codex"},
            {"model_id": "gpt-6-sol", "quality": 80.0, "quality_unit": "Composite /100", "subscription": "codex"}]
    out = [r["model_id"] for r in knowledge.tie_break(conn, "general", rows)]
    assert out == ["gpt-6-astra", "claude-opus-5-5", "claude-fable-5-1", "gpt-6-sol"]
