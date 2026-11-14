"""Reading a session slice by slice and a decision against its predecessors. walter-memory and the model are
simulated; cards and the database are real."""
import pytest

from walter_devboard import cards, llm, reading
from walter_devboard.config import Config

CFG = Config()
S = "codex/vm/t1"


@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: {"context", "memory", "router", "ops", "core"})


def slice_(lo, hi, more):
    return {"session": {"session_id": S, "runtime": "codex", "title": "t", "cwd": "/srv/dev"}, "from_seq": lo,
            "to_seq": hi, "more": more,
            "items": [{"seq": lo, "at": "2026-11-10 10:00:00+00:00", "kind": "user", "text": "fais le lot 3"},
                      {"seq": hi, "at": "2026-11-10 10:05:00+00:00", "kind": "assistant", "text": "fait, le lot avance"}]}


def answer(title, seq, dev=True):
    return {"is_walter_development": dev, "approvals": [],
            "cards": [] if not dev else [{"ref": None, "title": title, "module": "memory", "status": "in_progress",
                                          "owner": "codex", "change": "x", "deadline": None, "decisions": [],
                                          "files": [], "blocks": [], "evidence": [{"seq": seq, "quote": "lot"}]}]}


@pytest.fixture
def fake(monkeypatch):
    state = {"slices": {}, "answers": [], "reads": []}
    monkeypatch.setattr(reading, "_digest", lambda sid, after: state["slices"][after])

    def read(cfg, conn, *, key, kind, source_ref, from_seq, to_seq, prompt, schema, validate):
        state["reads"].append((kind, source_ref, from_seq, to_seq, prompt))
        a = state["answers"].pop(0)
        if isinstance(a, Exception):
            raise a
        validate(a)
        return a
    monkeypatch.setattr(reading.llm, "read", read)
    return state


def seq(conn):
    return conn.execute("select read_seq, dirty, state from devboard.sessions where session_id = %s", (S,)).fetchone()


def test_not_dev_session_skipped(conn, fake):
    fake["slices"] = {0: slice_(1, 9, False)}
    fake["answers"] = [answer("", 0, dev=False)]
    assert reading.read_session(CFG, conn, S) == "skipped"
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 0
    assert seq(conn)["read_seq"] == 9


def test_session_read_in_slices(conn, fake):
    fake["slices"] = {0: slice_(1, 9, True), 9: slice_(10, 20, False)}
    fake["answers"] = [answer("Mémoire : lot 3", 1), answer("Mémoire : lot 3 de l'extraction", 10)]
    assert reading.read_session(CFG, conn, S) == "done"
    assert [r[2:4] for r in fake["reads"]] == [(1, 9), (10, 20)]
    s = seq(conn)
    assert s["read_seq"] == 20 and s["dirty"] is False and s["state"] == "done"


def test_open_cards_given_to_the_model(conn, fake):
    fake["slices"] = {0: slice_(1, 9, True), 9: slice_(10, 20, False)}
    fake["answers"] = [answer("Mémoire : lot 3", 1), answer("Autre chose", 10)]
    reading.read_session(CFG, conn, S)
    assert "W-1" in fake["reads"][1][4][-1]["content"]


def test_pause_midway_resumes(conn, fake):
    fake["slices"] = {0: slice_(1, 9, True), 9: slice_(10, 20, False)}
    fake["answers"] = [answer("Mémoire : lot 3", 1), llm.Paused("quota")]
    assert reading.read_session(CFG, conn, S) == "paused"
    assert seq(conn)["read_seq"] == 9
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 1
    fake["answers"] = [answer("Router : autre", 10)]
    assert reading.read_session(CFG, conn, S) == "done"
    assert fake["reads"][-1][2] == 10 and seq(conn)["read_seq"] == 20


def test_failed_slice_keeps_position(conn, fake, monkeypatch):
    fake["slices"] = {0: slice_(1, 9, False)}
    fake["answers"] = [None]
    monkeypatch.setattr(reading.llm, "read", lambda *a, **k: None)
    assert reading.read_session(CFG, conn, S) == "failed"
    assert seq(conn)["read_seq"] == 0


def decisions(conn):
    for i, (anchor, title) in enumerate([("2026-11-01-ancienne", "Le modèle de décision choisit le spécialiste"),
                                         ("2026-11-13-nouvelle", "Le L2/L3 appelle des sous-agents")]):
        conn.execute("""insert into devboard.documents (path, title, kind, sha256) values ('D.md', 'D', 'decisions', 'x')
                        on conflict do nothing""")
        conn.execute("""insert into devboard.sections (doc_path, anchor, heading, level, line, body, sha256)
                        values ('D.md', %s, %s, 2, %s, %s, 'h')""", (anchor, title, i, f"## {title}\ncorps {i}"))
        conn.execute("""insert into devboard.decisions (doc_path, anchor, date, title, sha256)
                        values ('D.md', %s, %s, %s, 'h')""", (anchor, anchor[:10], title))


def test_decision_succession_written(conn, fake):
    decisions(conn)
    fake["answers"] = [{"succeeds": [{"anchor": "2026-11-01-ancienne", "quote": "remplace le choix du spécialiste"}]}]
    assert reading.read_decision(CFG, conn, 2) == "done"
    links = conn.execute("select newer_id, older_id, quote from devboard.decision_links").fetchall()
    assert links == [{"newer_id": 2, "older_id": 1, "quote": "remplace le choix du spécialiste"}]
    assert conn.execute("select read_sha256 from devboard.decisions where id = 2").fetchone()["read_sha256"] == "h"
    assert "Le modèle de décision choisit" in fake["reads"][0][4][-1]["content"]


def test_decision_unknown_anchor_refused(conn, fake):
    decisions(conn)
    fake["answers"] = [{"succeeds": [{"anchor": "2026-10-99-inventee", "quote": "x"}]}]
    with pytest.raises(ValueError):
        reading.read_decision(CFG, conn, 2)


def test_reading_checks_citations_against_the_shown_events(conn, fake):
    """The model cites seq 3, inside 1-5 but not shown (only 1 and 5 were): the reading is refused."""
    fake["slices"] = {0: slice_(1, 5, False)}
    fake["answers"] = [answer("Lot 3", 3)]
    with pytest.raises(ValueError, match="not shown"):
        reading.read_session(CFG, conn, S)
