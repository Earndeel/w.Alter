"""walter_memory.documents: sections of curated records, and the records excerpt of the memory context (offline)."""
from datetime import datetime, timezone

from walter_memory import context, documents


def test_h2_sections_dated_and_numbered(tmp_path):
    p = tmp_path / "DECISIONS.md"
    p.write_text("# Titre\nintro\n## 2026-10-28 — Sorties réseau\nChromium : Freebox.\n"
                 "## Questions ouvertes\nx\n## 2026-10-28 — Sorties réseau\nsuite\n")
    s = documents.sections(str(p), "h2")
    assert [x["key"] for x in s] == ["2026-10-28 — Sorties réseau", "Questions ouvertes", "2026-10-28 — Sorties réseau #2"]
    assert s[0]["date"] == datetime(2026, 10, 28, tzinfo=timezone.utc)
    assert "Freebox" in s[0]["text"] and "intro" not in s[0]["text"]


def test_file_section_drops_front_matter(tmp_path):
    p = tmp_path / "rule.md"
    p.write_text('---\nname: x\ndescription: "Images = best available"\n---\n\nBody of the rule.\n')
    (s,) = documents.sections(str(p), "file")
    assert s["title"] == "Images = best available" and s["text"] == "Body of the rule."


def test_window_keeps_the_part_that_answers():
    text = "a " * 900 + "le port de walter-exit-local est 1084" + " b" * 400
    w = context._window(text, "sur quel port écoute walter-exit-local ?", 300)
    assert "1084" in w and w.startswith("…")
    assert context._window("court", "x") == "court"


def test_form_preamble_left_out_of_the_search_query():
    sub = lambda s: context.FORM_PREAMBLE.sub("", s, count=1)          # noqa: E731
    assert sub("Sans utiliser aucun outil, réponds en une phrase : dans quel pays ?") == "dans quel pays ?"
    assert sub("Note : le port est 1084") == "Note : le port est 1084"
    assert sub("Quel est le port : 1084 ?") == "Quel est le port : 1084 ?"
