"""Read API and live stream. The server reads with its own connections, so the data here is committed (autocommit
connection) and wiped after each test. The stream is tested on a real uvicorn in a thread."""
import socket
import threading
import time
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from walter_devboard import cards, db, server

S = "claude_code/vm/abc"
LAYOUT = {"walter_root": "/walter", "modules": [
    {"id": "core", "vision_target": "/walter/core"}, {"id": "context", "vision_target": "/walter/cognition/context"},
    {"id": "memory", "vision_target": "/walter/cognition/memory"}, {"id": "ops", "vision_target": "/walter/ops"},
    {"id": "browse", "vision_target": "/walter/capabilities/browse"}]}
STATUS = {"modules": [{"id": m["id"], "runtime_health": "active"} for m in LAYOUT["modules"]]}


@pytest.fixture
def c(database, monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: {m["id"] for m in LAYOUT["modules"]})
    monkeypatch.setattr(server, "_layout", lambda: LAYOUT)
    monkeypatch.setattr(server, "_status", lambda: STATUS)
    with db.autocommit() as conn:
        yield conn
        conn.execute("""truncate devboard.cards, devboard.card_evidence, devboard.card_links, devboard.corrections,
                        devboard.documents, devboard.sections, devboard.decisions, devboard.decision_links,
                        devboard.activity, devboard.live, devboard.state restart identity cascade""")


@pytest.fixture
def api():
    return TestClient(server.app)


def card(conn, title, module="context", status="in_progress", **kw):
    c = {"ref": None, "title": title, "module": module, "status": status, "owner": "claude_code", "change": "x",
         "deadline": None, "decisions": [], "files": [], "blocks": [], "evidence": [{"seq": 3, "quote": "q"}]}
    c.update(kw)
    return cards.apply(conn, S, 1, 9, {"is_walter_development": True, "approvals": [], "cards": [c]})[0]


def test_inbox_lists_waiting_with_days(c, api):
    card(c, "Valider le jeu 3", status="waiting_owner")
    card(c, "Autre chose", module="memory")
    c.execute("update devboard.cards set waiting_since = now() - interval '4 days' where id = 1")
    r = api.get("/api/inbox").json()
    assert [x["ref"] for x in r] == ["W-1"] and r[0]["flags"]["waiting_days"] == 4


def test_cards_grouped_order(c, api):
    card(c, "Fini", status="done")
    card(c, "Abandon", module="memory", status="abandoned")
    card(c, "En pause", module="ops", status="paused")
    card(c, "Oublié", module="core")
    c.execute("update devboard.cards set last_activity_at = now() - interval '9 days' where id = 4")
    card(c, "En cours", module="browse")
    card(c, "Attente", module="memory", status="waiting_owner")
    groups = api.get("/api/cards?group=status").json()
    assert [g["key"] for g in groups] == ["waiting_owner", "in_progress", "late_or_stale", "paused", "done", "abandoned"]
    by = {g["key"]: [x["title"] for x in g["cards"]] for g in groups}
    assert by["late_or_stale"] == ["Oublié"] and by["in_progress"] == ["En cours"]
    assert api.get("/api/cards?q=pause").json()[3]["cards"][0]["title"] == "En pause"
    mods = api.get("/api/cards?group=module").json()
    assert "memory" in [g["key"] for g in mods]


def decisions(conn):
    conn.execute("insert into devboard.documents (path, title, kind, sha256) values ('/d/DECISIONS.md', 'D', 'decisions', 'x')")
    for i, (anchor, d, title) in enumerate([("2026-11-01-ancienne", "2026-11-01", "Le modèle choisit le spécialiste"),
                                            ("2026-11-13-nouvelle", "2026-11-13", "Le L2 appelle des sous-agents")]):
        conn.execute("""insert into devboard.sections (doc_path, anchor, heading, level, line, body, sha256)
                        values ('/d/DECISIONS.md', %s, %s, 2, %s, %s, 'h')""", (anchor, title, i, f"## {title}\ncorps"))
        conn.execute("insert into devboard.decisions (doc_path, anchor, date, title, sha256) values ('/d/DECISIONS.md', %s, %s, %s, 'h')",
                     (anchor, d, title))
    conn.execute("insert into devboard.decision_links (newer_id, older_id, quote) values (2, 1, 'remplace le choix')")


def test_card_detail_shows_replaced_decision(c, api):
    decisions(c)
    card(c, "Spécialistes", decisions=["2026-11-01-ancienne"], files=["/walter/x.md"])
    r = api.get("/api/cards/W-1").json()
    [d] = r["decisions"]
    assert d["anchor"] == "2026-11-01-ancienne"
    assert d["replaced_by"][0]["anchor"] == "2026-11-13-nouvelle" and d["replaced_by"][0]["date"] == "2026-11-13"
    assert d["replaced_by"][0]["quote"] == "remplace le choix"
    assert r["files"] == ["/walter/x.md"] and r["evidence"][0]["quote"] == "q" and r["activity"]
    assert api.get("/api/cards/W-99").status_code == 404


def test_decisions_replaced_filter(c, api):
    decisions(c)
    c.execute("insert into devboard.decisions (doc_path, anchor, date, title, sha256) values ('/d/DECISIONS.md', 'seule', '2026-11-02', 'seule', 'h')")
    all_ = api.get("/api/decisions").json()
    replaced = api.get("/api/decisions?replaced=1").json()
    assert len(all_) == 3 and {d["anchor"] for d in replaced} == {"2026-11-01-ancienne", "2026-11-13-nouvelle"}
    new = next(d for d in replaced if d["anchor"] == "2026-11-13-nouvelle")
    assert new["replaces"][0]["anchor"] == "2026-11-01-ancienne"


def test_docs_refuses_unknown_path(c, api, tmp_path):
    f = tmp_path / "VISION.md"
    f.write_text("# Vision\n\n## Core\ntexte core\n")
    c.execute("insert into devboard.documents (path, title, kind, sha256) values (%s, 'Vision', 'vision', 'x')", (str(f),))
    c.execute("""insert into devboard.sections (doc_path, anchor, heading, level, line, body, sha256)
                 values (%s, 'core', 'Core', 2, 3, '## Core' || chr(10) || 'texte core', 'h')""", (str(f),))
    r = api.get("/api/docs/../../etc/passwd")          # the URL is normalised to /etc/passwd: never the file
    assert r.status_code != 200 or "root:" not in r.text
    assert api.get("/api/docs/%2E%2E/%2E%2E/etc/passwd").status_code == 404
    assert api.get("/api/docs/etc/passwd").status_code == 404
    other = tmp_path / "AUTRE.md"
    other.write_text("secret")
    assert api.get(f"/api/docs{other}").status_code == 404
    assert "texte core" in api.get(f"/api/docs{f}").json()["markdown"]
    assert api.get(f"/api/docs{f}?anchor=core").json()["markdown"].startswith("## Core")
    assert [d["path"] for d in api.get("/api/docs").json()] == [str(f)]


def test_vision_colours(c, api):
    card(c, "En retard", module="context", deadline=(date.today() - timedelta(days=2)).isoformat())
    card(c, "Attente", module="memory", status="waiting_owner")
    card(c, "Fini", module="ops", status="done")
    card(c, "En cours", module="browse")
    comps = api.get("/api/vision").json()
    assert [x["key"] for x in comps] == ["core", "cognition", "capabilities", "ops", "lab"]
    colour = {m["id"]: m["color"] for x in comps for m in x["modules"]}
    assert colour == {"context": "red", "memory": "amber", "ops": "green", "browse": "blue", "core": "blue"}
    assert next(m for x in comps for m in x["modules"] if m["id"] == "ops")["health"] == "active"


def test_today_and_live(c, api):
    card(c, "Tableau")
    c.execute("insert into devboard.live (session_id, runtime, title, card_id) values (%s, 'claude_code', 'tableau', 1)", (S,))
    today = api.get("/api/today").json()
    assert today[0]["ref"] == "W-1"
    live = api.get("/api/live").json()
    assert live[0]["runtime"] == "claude_code" and live[0]["ref"] == "W-1"
    s = api.get("/api/summary").json()
    assert s["open"] == 1 and s["inbox"] == 0 and s["live"] == 1


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_stream_relays_notify(c):
    import uvicorn
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    got = []

    def listen():
        with httpx.stream("GET", f"http://127.0.0.1:{port}/api/stream", timeout=10) as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                got.append(line)
                if line.startswith("event: change"):
                    return
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.5)
    sent = time.monotonic()
    db.notify(c, "cards", refs=["W-1"])
    t.join(timeout=2)
    srv.should_exit = True
    assert any(l.startswith("event: change") for l in got) and time.monotonic() - sent < 2.5
