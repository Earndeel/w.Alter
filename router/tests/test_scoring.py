from __future__ import annotations

import pytest

from walter_router import collect, db, dossier, scoring


def _row(model, score, votes=None):
    return {"model_id": model, "variant": "", "score": score, "score_unit": "Elo",
            "extra": {"votes": votes} if votes else {}}


def test_board_scale_is_linear_from_median_to_leader():
    q = scoring.board_quality([_row("a", 1500), _row("b", 1450), _row("c", 1400), _row("d", 1300), _row("e", 1200)])
    assert q["a"]["q"] == 100 and q["c"]["q"] == 0 and q["b"]["q"] == pytest.approx(50) and q["e"]["q"] == 0


def test_reliability_follows_votes_and_provisional_rows():
    assert scoring._reliability(_row("a", 1, votes=500)) == pytest.approx(0.5)
    assert scoring._reliability({"extra": {"provisional": True}}) == 0.5
    assert scoring._reliability({"extra": {}}) == 1.0


def test_bridgebench_rows_are_read_from_the_page():
    page = ('x{"id":"openai/gpt-6-luna","href":"/leaderboard/gpt-6-luna","name":"GPT-6 Luna","provisional":false,'
            '"scores":{"overall":513,"frontend":460,"oneShot":480}}y')
    rows = collect.parse_benchmarks("bridgebench", {"rows": collect.bridgebench_rows(page)})
    assert {(r["model_id"], r["task"], r["score"]) for r in rows} == {
        ("gpt-6-luna", "overall", 513), ("gpt-6-luna", "frontend", 460), ("gpt-6-luna", "one_shot", 480)}


@pytest.fixture
def conn():
    with db.connect() as c:
        if c.execute("select to_regclass('models.latest_dossiers') as t").fetchone()["t"] is None:
            pytest.skip("schema 007 not migrated")
        yield c
        c.rollback()


def test_composite_mixes_every_board_of_the_task(conn):
    top = scoring.composite(conn, "coding")[0]
    assert len(top["boards"]) >= 3 and 0 < top["composite"] <= 100


def test_dossier_carries_roles_candidates_and_rules(conn):
    d = dossier.latest(conn, "text_to_video")
    if d is None:
        pytest.skip("no dossier yet")
    assert {r["role"] for r in d["roles"]} >= {"default", "premium", "ugc"} and d["candidates"] and d["rules"]
