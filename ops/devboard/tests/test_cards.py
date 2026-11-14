"""From a model reading to cards: evidence required and inside the read range, unknown refs/anchors/modules refused,
same chantier merged, owner corrections never overwritten, approvals unblock a waiting card, flags."""
from datetime import date, datetime, timedelta, timezone

import pytest

from walter_devboard import cards

S = "claude_code/vm/abc"


@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: {"context", "memory", "router", "ops", "core"})


def card(title="Preflight P1 : activer le jeu 3", module="context", status="in_progress", ref=None, seq=5, **kw):
    c = {"ref": ref, "title": title, "module": module, "status": status, "owner": "claude_code",
         "change": "Le modèle comprend le message.", "deadline": None, "decisions": [], "files": [], "blocks": [],
         "evidence": [{"seq": seq, "quote": "on active le jeu 3"}]}
    c.update(kw)
    return c


def apply(conn, *cs, approvals=(), lo=1, hi=10, session=S):
    return cards.apply(conn, session, lo, hi, {"is_walter_development": True, "cards": list(cs),
                                               "approvals": list(approvals)})


def one(conn, ref):
    return conn.execute("select * from devboard.cards where ref = %s", (ref,)).fetchone()


def test_new_card_gets_ref(conn):
    assert apply(conn, card()) == ["W-1"]
    assert apply(conn, card(title="Router : calibrer la décision", module="router")) == ["W-2"]
    ev = conn.execute("select kind, source_ref, seq, quote from devboard.card_evidence").fetchall()
    assert ev[0] == {"kind": "session", "source_ref": S, "seq": 5, "quote": "on active le jeu 3"}


def test_card_without_evidence_rejected(conn):
    assert apply(conn, card(evidence=[])) == []
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 0


def test_evidence_out_of_range_rejected(conn):
    assert apply(conn, card(seq=11)) == []
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 0


def test_unknown_ref_fails_validation(conn):
    with pytest.raises(ValueError):
        apply(conn, card(ref="W-99"))


def test_unknown_module_fails_validation(conn):
    with pytest.raises(ValueError):
        apply(conn, card(module="cuisine"))


def test_unknown_decision_anchor_fails_validation(conn):
    with pytest.raises(ValueError):
        apply(conn, card(decisions=["2026-13-40-nulle-part"]))


def test_known_decision_linked(conn):
    conn.execute("""insert into devboard.decisions (doc_path, anchor, date, title, sha256)
                    values ('DECISIONS.md', '2026-11-13-specialite', '2026-11-13', 'spécialité', 'x')""")
    [ref] = apply(conn, card(decisions=["2026-11-13-specialite"], files=["/walter/x.py"]))
    links = conn.execute("select kind, target from devboard.card_links order by kind").fetchall()
    assert links == [{"kind": "decision", "target": "2026-11-13-specialite"}, {"kind": "file", "target": "/walter/x.py"}]


def test_similar_title_same_module_merged(conn):
    apply(conn, card("Preflight P1 : activer le jeu 3"))
    assert apply(conn, card("Activer le jeu de questions 3 du Preflight P1", status="waiting_owner")) == ["W-1"]
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 1
    assert one(conn, "W-1")["status"] == "waiting_owner"


def test_similar_title_other_number_not_merged(conn):
    apply(conn, card("Preflight P1 : activer le jeu 3"))
    apply(conn, card("Preflight P1 : activer le jeu 4"))
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 2


def test_similar_title_other_module_not_merged(conn):
    apply(conn, card("Nettoyage, phase 3", module="memory"))
    apply(conn, card("Nettoyage, phase 3", module="router"))
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 2


def test_correction_wins(conn):
    apply(conn, card())
    conn.execute("""insert into devboard.corrections (card_id, field, value, reason)
                    values (1, 'status', '"done"', 'fini hier')""")
    conn.execute("update devboard.cards set status = 'done' where id = 1")
    apply(conn, card(ref="W-1", status="in_progress", change="autre texte"))
    c = one(conn, "W-1")
    assert c["status"] == "done" and c["change"] == "autre texte"


def test_approval_moves_waiting_to_in_progress(conn):
    apply(conn, card(status="waiting_owner"))
    assert one(conn, "W-1")["waiting_since"] is not None
    assert apply(conn, approvals=[{"ref": "W-1", "seq": 7, "quote": "oui vas-y"}], lo=6, hi=9) == ["W-1"]
    c = one(conn, "W-1")
    assert c["status"] == "in_progress" and c["waiting_since"] is None
    assert conn.execute("select count(*) n from devboard.card_evidence where quote = 'oui vas-y'").fetchone()["n"] == 1


def test_activity_written_per_card(conn):
    at = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    cards.apply(conn, S, 1, 10, {"is_walter_development": True, "cards": [card()], "approvals": []}, at=at)
    act = conn.execute("select kind, source_ref, card_id from devboard.activity").fetchall()
    assert act == [{"kind": "reading", "source_ref": f"{S}#1-10", "card_id": 1}]
    assert one(conn, "W-1")["last_activity_at"] == at


def test_flags_waiting_never_late(conn):
    apply(conn, card(status="waiting_owner", deadline="2026-11-01"))
    conn.execute("update devboard.cards set waiting_since = now() - interval '10 days'")
    f = cards.flags(conn, one(conn, "W-1"), date.today())
    assert f["waiting_days"] == 10 and f["late"] is False


def test_flags_late_when_deadline_passed(conn):
    apply(conn, card(deadline=(date.today() - timedelta(days=1)).isoformat()))
    assert cards.flags(conn, one(conn, "W-1"), date.today())["late"] is True


def test_flags_stale_after_7_days(conn):
    apply(conn, card())
    conn.execute("update devboard.cards set last_activity_at = now() - interval '8 days'")
    f = cards.flags(conn, one(conn, "W-1"), date.today())
    assert f["stale"] is True and f["waiting_days"] is None
    conn.execute("update devboard.cards set last_activity_at = now() - interval '2 days'")
    assert cards.flags(conn, one(conn, "W-1"), date.today())["stale"] is False
