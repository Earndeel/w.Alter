"""The owner's buttons: « Abandonner » and « Reprendre ». The engine is a fake (no turn ever runs); the HTTP doors are
tested on the loopback listener (buttons) and the tailnet one (refused)."""
import pytest
from fastapi.testclient import TestClient

from walter_devboard import actions, cards, db, server

S = "claude_code/vm/abc"
MODULES = {"context", "memory", "ops", "core"}


class FakeEngine:
    def __init__(self):
        self.ops, self.results = [], {}

    def op(self, body, timeout=30):
        self.ops.append(body)
        if body["op"] == "session.open":
            return {"session_id": f"web/owner/{body['conversation']}", "walter_session": "dsh/vm/session-k1",
                    "resumed": False}
        if body["op"] == "turn.submit":
            return {"accepted": True, "session_id": body["session_id"], "request_id": body["idempotency_key"],
                    "walter_session": "dsh/vm/session-k1"}
        if body["op"] == "turn.result":
            return {"result": self.results.get(body["request_id"], {"done": False, "status": "running", "text": ""})}
        if body["op"] == "turn.cancel":
            return {"ok": True}
        raise AssertionError(body)


def cfg(**kw):
    c = server.config.Config(owner_name="Camille", actions_port=3094, actions_host="127.0.0.1",
                             engine_token_file=None, notify_command=[])
    for k, v in kw.items():
        setattr(c, k, v)
    return c


@pytest.fixture
def c(database, monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: MODULES)
    with db.autocommit() as conn:
        yield conn
        conn.execute("""truncate devboard.cards, devboard.card_evidence, devboard.card_links, devboard.corrections,
                        devboard.activity, devboard.live, devboard.resumes restart identity cascade""")


def card(conn, title="Vocaux Instagram", status="in_progress"):
    return cards.apply(conn, S, 1, 9, {"is_walter_development": True, "approvals": [], "cards": [
        {"ref": None, "title": title, "module": "memory", "status": status, "owner": "claude_code",
         "change": "Les vocaux sont transcrits.", "deadline": None, "decisions": [], "files": ["/walter/x.py"],
         "blocks": [], "evidence": [{"seq": 3, "quote": "les vocaux Instagram sont rangés en vidéo"}]}]})[0]


def status(conn, ref):
    return conn.execute("select status from devboard.cards where ref = %s", (ref,)).fetchone()["status"]


def test_brief_carries_card_note_evidence_and_outcome_rule(c):
    card(c)
    text = actions.brief(c, "W-1", "commence par le backfill")
    assert "W-1" in text and "Vocaux Instagram" in text and "commence par le backfill" in text
    assert "les vocaux Instagram sont rangés en vidéo" in text and "/walter/x.py" in text
    assert "ÉTAT: done" in text and "relit avant l'envoi" in text


def test_resume_opens_the_card_conversation_and_records_it(c):
    card(c, status="waiting_owner")
    eng = FakeEngine()
    with c.transaction():
        out = actions.resume(c, cfg(), eng, "W-1", "vas-y")
    assert [o["op"] for o in eng.ops] == ["session.open", "turn.submit"]
    assert eng.ops[0]["interface"] == "web" and eng.ops[0]["conversation"] == "devboard-w-1"
    assert eng.ops[0]["principal"] == {"kind": "owner", "id": "owner"}
    assert eng.ops[1]["idempotency_key"] == out["request_id"] and "vas-y" in eng.ops[1]["message"]["text"]
    assert status(c, "W-1") == "in_progress"
    row = c.execute("select * from devboard.resumes").fetchone()
    assert row["status"] == "running" and row["status_before"] == "waiting_owner" and row["note"] == "vas-y"
    assert c.execute("select card_id from devboard.live").fetchone()["card_id"] == 1


def test_second_resume_refused_while_running(c):
    card(c)
    eng = FakeEngine()
    with c.transaction():
        actions.resume(c, cfg(), eng, "W-1")
    with pytest.raises(actions.ActionError) as e:
        with c.transaction():
            actions.resume(c, cfg(), eng, "W-1")
    assert e.value.status == 409


def test_follow_applies_the_stated_outcome(c, monkeypatch):
    card(c)
    eng = FakeEngine()
    with c.transaction():
        out = actions.resume(c, cfg(), eng, "W-1")
    assert actions.follow_once(cfg(), eng) == []                        # still running: nothing changes
    eng.results[out["request_id"]] = {"done": True, "status": "ok",
                                      "text": "Backfill fait, 71 vocaux transcrits et vérifiés.\nÉTAT: done"}
    told = []
    monkeypatch.setattr(actions, "_notify", lambda cfg_, text: told.append(text))     # no real Telegram
    done = actions.follow_once(cfg(), eng)
    assert done == [{"ref": "W-1", "status": "ok", "outcome": "done"}]
    assert status(c, "W-1") == "done"
    row = c.execute("select status, outcome, summary from devboard.resumes").fetchone()
    assert row["outcome"] == "done" and "71 vocaux" in row["summary"] and "ÉTAT" not in row["summary"]
    assert c.execute("select count(*) n from devboard.live").fetchone()["n"] == 0
    assert told and "W-1" in told[0] and "fini" in told[0]
    by = c.execute("select by from devboard.corrections order by id desc limit 1").fetchone()["by"]
    assert by == actions.BY


def test_follow_without_outcome_keeps_the_card(c):
    card(c)
    eng = FakeEngine()
    with c.transaction():
        out = actions.resume(c, cfg(), eng, "W-1")
    eng.results[out["request_id"]] = {"done": True, "status": "error", "text": "ÉTAT: done"}
    actions.follow_once(cfg(), eng)
    assert status(c, "W-1") == "in_progress"                             # an error never closes a card
    assert c.execute("select status, outcome from devboard.resumes").fetchone() == {"status": "error", "outcome": None}


def test_abandon_cancels_a_running_resume(c):
    card(c)
    eng = FakeEngine()
    with c.transaction():
        actions.resume(c, cfg(), eng, "W-1")
    with c.transaction():
        out = actions.abandon(c, eng, "W-1", "plus d'actualité")
    assert eng.ops[-1]["op"] == "turn.cancel" and out["cancelled_resume"] == 1
    assert status(c, "W-1") == "abandoned"
    assert c.execute("select reason from devboard.corrections order by id desc limit 1").fetchone()["reason"] == \
        "plus d'actualité"


def test_outcome_line_last_one_wins():
    assert actions.outcome_of("ÉTAT: in_progress\nencore\nÉTAT : `waiting_owner`") == "waiting_owner"
    assert actions.outcome_of("rien") is None


@pytest.fixture
def web(c, monkeypatch):
    eng = FakeEngine()
    server._cfg.clear()
    server._cfg.append(cfg())
    monkeypatch.setattr(server, "_engine", lambda: eng)
    monkeypatch.setattr(server, "_layout", lambda: {"walter_root": "/walter", "modules": []})
    yield eng
    server._cfg.clear()


H = {"x-walter-action": "1", "content-type": "application/json"}


def test_buttons_only_on_the_loopback_listener(web, c):
    card(c)
    tailnet = TestClient(server.app, base_url="http://100.64.0.1:3093")
    assert tailnet.get("/api/summary").json()["actions"] is False
    assert tailnet.post("/api/actions/abandon", json={"ref": "W-1"}, headers=H).status_code == 403
    local = TestClient(server.app, base_url="http://127.0.0.1:3094")
    assert local.get("/api/summary").json()["actions"] is True
    assert local.post("/api/actions/abandon", json={"ref": "W-1"}).status_code == 400      # no action header
    r = local.post("/api/actions/abandon", json={"ref": "W-1", "reason": "fait ailleurs"}, headers=H)
    assert r.status_code == 200 and status(c, "W-1") == "abandoned"


def test_resume_over_http_and_card_detail_shows_it(web, c):
    card(c, status="paused")
    local = TestClient(server.app, base_url="http://127.0.0.1:3094")
    r = local.post("/api/actions/resume", json={"ref": "W-1", "note": "go"}, headers=H)
    assert r.status_code == 200 and r.json()["walter_session"] == "dsh/vm/session-k1"
    assert local.post("/api/actions/resume", json={"ref": "W-1"}, headers=H).status_code == 409
    d = local.get("/api/cards/W-1").json()
    assert d["status"] == "in_progress" and d["resumes"][0]["status"] == "running"
    assert local.post("/api/actions/resume", json={"ref": "W-99"}, headers=H).status_code == 404
