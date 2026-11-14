"""Documents and decisions are read as they are, section by section (no model)."""
from walter_devboard import docs
from walter_devboard.config import Config

DECISIONS = """# Décisions

## 2026-11-13 — Drex Max 1.1 devient le modèle de décision par défaut
Mercury est remplacé.

## 2026-11-13 — La spécialité n'est plus choisie par le modèle de décision
Le L2/L3 appelle des sous-agents.

```
## 2026-01-01 — pas un titre (bloc de code)
```

## 2026-11-14 — Preflight : jeu de questions 3
Préparé.
"""


def cfg(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "DECISIONS.md").write_text(DECISIONS)
    (d / "VISION.md").write_text("# Vision\n\n## 1. Fondamental\ntexte\n\n## Notes\na\n\n## Notes\nb\n")
    r = tmp_path / "reports"
    r.mkdir()
    return Config(docs_dir=d, reports_dir=r)


def test_decisions_parsed(conn, tmp_path):
    c = cfg(tmp_path)
    res = docs.sync(conn, c, module_roots=[])
    rows = conn.execute("select date::text, title from devboard.decisions order by id").fetchall()
    assert res["decisions_new"] == 3
    assert [r["date"] for r in rows] == ["2026-11-13", "2026-11-13", "2026-11-14"]
    assert rows[0]["title"] == "Drex Max 1.1 devient le modèle de décision par défaut"


def test_section_anchor_unique(conn, tmp_path):
    c = cfg(tmp_path)
    docs.sync(conn, c, module_roots=[])
    anchors = [r["anchor"] for r in conn.execute(
        "select anchor from devboard.sections where doc_path like '%VISION.md' order by line").fetchall()]
    assert anchors == ["vision", "1-fondamental", "notes", "notes-2"]


def test_changed_section_rehashed(conn, tmp_path):
    c = cfg(tmp_path)
    docs.sync(conn, c, module_roots=[])
    before = conn.execute("select sha256 from devboard.decisions order by id limit 1").fetchone()["sha256"]
    (c.docs_dir / "DECISIONS.md").write_text(DECISIONS.replace("Mercury est remplacé.", "Mercury est retiré."))
    res = docs.sync(conn, c, module_roots=[])
    after = conn.execute("select sha256 from devboard.decisions order by id limit 1").fetchone()["sha256"]
    assert res["decisions_changed"] == 1 and before != after


def test_removed_section_kept(conn, tmp_path):
    c = cfg(tmp_path)
    docs.sync(conn, c, module_roots=[])
    (c.docs_dir / "DECISIONS.md").write_text(DECISIONS.split("## 2026-11-14")[0])
    res = docs.sync(conn, c, module_roots=[])
    row = conn.execute("select removed_at from devboard.decisions where date = '2026-11-14'").fetchone()
    assert row is not None and row["removed_at"] is not None and res["removed"] >= 1


def test_resync_idempotent(conn, tmp_path):
    c = cfg(tmp_path)
    docs.sync(conn, c, module_roots=[])
    res = docs.sync(conn, c, module_roots=[])
    assert res["sections_changed"] == 0 and res["decisions_new"] == 0 and res["decisions_changed"] == 0
    assert res["removed"] == 0


def test_module_docs_and_reports(conn, tmp_path):
    c = cfg(tmp_path)
    mod = tmp_path / "memory"
    (mod / "docs").mkdir(parents=True)
    (mod / "docs" / "PLAN.md").write_text("# Plan\n## P1\nx\n")
    (c.reports_dir / "2026-11-14-rapport.md").write_text("# Rapport\n")
    docs.sync(conn, c, module_roots=[mod])
    kinds = {r["kind"] for r in conn.execute("select kind from devboard.documents").fetchall()}
    assert {"module", "report", "decisions", "vision"} <= kinds
