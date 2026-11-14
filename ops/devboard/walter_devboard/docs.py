"""Documents as they are: VISION, DECISIONS, V1, ARCHITECTURE, RUNBOOK, each module's docs/ and the reports, split
into sections. A decision = a level-2 section of DECISIONS.md whose title starts with a date. No model here."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .db import notify

GLOBAL = {"VISION.md": "vision", "DECISIONS.md": "decisions", "V1.md": "v1", "ARCHITECTURE.md": "architecture",
          "RUNBOOK.md": "runbook"}
HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
DECISION = re.compile(r"^(\d{4}-\d{2}-\d{2})\b[^\wÀ-ÿ`*]*(.*)$")


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "section"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sections(text: str) -> list[dict]:
    """Headings outside code fences, each with its body up to the next heading of the same or a higher level."""
    lines, heads, fence = text.splitlines(), [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        m = None if fence else HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    out, seen = [], {}
    for k, (i, level, heading) in enumerate(heads):
        end = next((j for j, lv, _ in heads[k + 1:] if lv <= level), len(lines))
        base = slug(heading)
        seen[base] = seen.get(base, 0) + 1
        anchor = base if seen[base] == 1 else f"{base}-{seen[base]}"
        body = "\n".join(lines[i + 1:end]).strip("\n")
        out.append({"anchor": anchor, "heading": heading, "level": level, "line": i + 1, "body": body,
                    "sha256": _sha(heading + "\n" + body)})
    return out


def documents(cfg: Config, module_roots: list[Path]) -> list[tuple[Path, str]]:
    out = [(cfg.docs_dir / name, kind) for name, kind in GLOBAL.items() if (cfg.docs_dir / name).is_file()]
    seen = {p.resolve() for p, _ in out}
    for root in module_roots:
        for p in sorted((root / "docs").glob("*.md")):
            if p.resolve() not in seen:
                seen.add(p.resolve())
                out.append((p, "module"))
    if cfg.reports_dir and cfg.reports_dir.is_dir():
        out += [(p, "report") for p in sorted(cfg.reports_dir.glob("*.md")) if p.resolve() not in seen]
    return out


def sync(conn, cfg: Config, module_roots: list[Path] | None = None) -> dict:
    if module_roots is None:
        from .config import module_roots as roots
        module_roots = roots()
    res = {"documents": 0, "sections_changed": 0, "decisions_new": 0, "decisions_changed": 0, "removed": 0}
    present = set()
    for path, kind in documents(cfg, module_roots):
        text = path.read_text(errors="replace")
        key, sha = str(path), _sha(text)
        present.add(key)
        res["documents"] += 1
        old = conn.execute("select sha256 from devboard.documents where path = %s", (key,)).fetchone()
        if old and old["sha256"] == sha:
            continue
        secs = sections(text)
        title = next((s["heading"] for s in secs if s["level"] == 1), path.stem)
        conn.execute("""insert into devboard.documents (path, title, kind, sha256, mtime) values (%s, %s, %s, %s, %s)
                        on conflict (path) do update set title = excluded.title, kind = excluded.kind,
                        sha256 = excluded.sha256, mtime = excluded.mtime""",
                     (key, title, kind, sha, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)))
        known = {r["anchor"]: r for r in conn.execute(
            "select anchor, sha256, removed_at from devboard.sections where doc_path = %s", (key,)).fetchall()}
        for s in secs:
            k = known.get(s["anchor"])
            if k and k["sha256"] == s["sha256"] and k["removed_at"] is None:
                continue
            res["sections_changed"] += 1
            conn.execute("""insert into devboard.sections (doc_path, anchor, heading, level, line, body, sha256)
                            values (%(doc)s, %(anchor)s, %(heading)s, %(level)s, %(line)s, %(body)s, %(sha256)s)
                            on conflict (doc_path, anchor) do update set heading = excluded.heading,
                            level = excluded.level, line = excluded.line, body = excluded.body,
                            sha256 = excluded.sha256, removed_at = null""", {"doc": key, **s})
        gone = [a for a, r in known.items() if r["removed_at"] is None and a not in {s["anchor"] for s in secs}]
        if gone:
            conn.execute("""update devboard.sections set removed_at = now() where doc_path = %s and anchor = any(%s)""",
                         (key, gone))
            res["removed"] += len(gone)
        if kind == "decisions":
            _decisions(conn, key, secs, res)
    if res["sections_changed"] or res["removed"]:
        notify(conn, "docs", **res)
    return res


def _decisions(conn, doc: str, secs: list[dict], res: dict) -> None:
    current = set()
    for s in secs:
        m = DECISION.match(s["heading"]) if s["level"] == 2 else None
        if not m:
            continue
        current.add(s["anchor"])
        title = m.group(2).strip() or s["heading"]
        old = conn.execute("select sha256, removed_at from devboard.decisions where anchor = %s", (s["anchor"],)).fetchone()
        if old is None:
            res["decisions_new"] += 1
        elif old["sha256"] != s["sha256"]:
            res["decisions_changed"] += 1
        elif old["removed_at"] is None:
            continue
        conn.execute("""insert into devboard.decisions (doc_path, anchor, date, title, sha256) values (%s, %s, %s, %s, %s)
                        on conflict (anchor) do update set title = excluded.title, sha256 = excluded.sha256,
                        date = excluded.date, removed_at = null""", (doc, s["anchor"], m.group(1), title, s["sha256"]))
    gone = conn.execute("""update devboard.decisions set removed_at = now()
                           where doc_path = %s and removed_at is null and not (anchor = any(%s)) returning id""",
                        (doc, list(current))).fetchall()
    res["removed"] += len(gone)
