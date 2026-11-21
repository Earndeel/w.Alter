"""Owner corrections: refused on an unknown card or field, applied at once, and never overwritten by a reading."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from walter_devboard import cards, correct

S = "claude_code/vm/abc"


@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: {"context", "memory", "router", "ops", "core"})


def make(conn, status="in_progress"):
    return cards.apply(conn, S, 1, 9, {"is_walter_development": True, "approvals": [], "cards": [
        {"ref": None, "title": "Tableau", "module": "ops", "status": status, "owner": "claude_code", "change": "x",
         "deadline": None, "decisions": [], "files": [], "blocks": [], "evidence": [{"seq": 3, "quote": "q"}]}]})


def test_correct_rejects_unknown_ref(conn):
    with pytest.raises(ValueError):
        correct.correct(conn, {"ref": "W-42", "field": "status", "value": "done", "reason": "fini"})


def test_correct_rejects_bad_value(conn):
    make(conn)
    with pytest.raises(ValueError):
        correct.correct(conn, {"ref": "W-1", "field": "status", "value": "presque", "reason": "?"})
    with pytest.raises(ValueError):
        correct.correct(conn, {"ref": "W-1", "field": "couleur", "value": "bleu", "reason": "?"})


def test_correct_writes_and_wins(conn):
    make(conn)
    out = correct.correct(conn, {"ref": "W-1", "field": "status", "value": "done", "reason": "fini hier"})
    assert out["ok"] and out["ref"] == "W-1"
    c = conn.execute("select status from devboard.cards where id = 1").fetchone()
    assert c["status"] == "done"
    row = conn.execute("select field, value, reason, by from devboard.corrections").fetchone()
    assert row == {"field": "status", "value": "done", "reason": "fini hier", "by": "owner"}
    cards.apply(conn, S, 10, 19, {"is_walter_development": True, "approvals": [], "cards": [
        {"ref": "W-1", "title": "Tableau", "module": "ops", "status": "in_progress", "owner": "claude_code",
         "change": "y", "deadline": None, "decisions": [], "files": [], "blocks": [],
         "evidence": [{"seq": 12, "quote": "q"}]}]})
    assert conn.execute("select status from devboard.cards where id = 1").fetchone()["status"] == "done"
    act = conn.execute("select text from devboard.activity where kind = 'correction'").fetchone()
    assert "fini hier" in act["text"]


def test_correct_decision_link(conn):
    make(conn)
    conn.execute("""insert into devboard.decisions (doc_path, anchor, date, title, sha256)
                    values ('D.md', '2026-11-13-x', '2026-11-13', 'x', 'h')""")
    correct.correct(conn, {"ref": "W-1", "field": "decision_link", "value": "2026-11-13-x", "reason": "lié"})
    assert conn.execute("select target from devboard.card_links where kind = 'decision'").fetchone()["target"] == \
        "2026-11-13-x"


def test_cli_reports_errors_as_json(database):
    root = Path(__file__).resolve().parent.parent
    p = subprocess.run([sys.executable, "-m", "walter_devboard.cli", "correct"], cwd=root, capture_output=True,
                       text=True, input=json.dumps({"ref": "W-999", "field": "status", "value": "done", "reason": "x"}))
    assert p.returncode == 2 and json.loads(p.stdout)["ok"] is False
