"""Model readings become cards (chantiers). The rules that keep the board honest live here, not in the prompt:
every card carries evidence from the slice that was read, unknown refs/anchors/modules fail the reading, the same
chantier is merged instead of duplicated, an owner correction is never overwritten."""
from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache

from . import db

STATUSES = ("waiting_owner", "in_progress", "paused", "done", "abandoned")
OWNERS = ("owner", "claude_code", "codex", "walter")
FIELDS = ("title", "module", "status", "owner", "change", "deadline")
MERGE_AT = 0.85
STOP = {"le", "la", "les", "l", "de", "du", "des", "d", "un", "une", "et", "a", "au", "aux", "en", "pour", "sur",
        "the", "of", "to", "and"}


@lru_cache(maxsize=1)
def _layout_modules() -> frozenset:
    out = subprocess.run(["walter", "layout", "show"], capture_output=True, text=True, check=True, timeout=60).stdout
    return frozenset(m["id"] for m in json.loads(out)["modules"])


def known_modules() -> set:
    return set(_layout_modules())


def _tokens(title: str) -> list[str]:
    t = unicodedata.normalize("NFKD", title.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return [w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP]


def similarity(a: str, b: str) -> float:
    """Same chantier said two ways: difflib on the sorted content words, or one title's words all contained in the
    other's (at least 3 words). Different numbers (« jeu 3 » / « jeu 4 ») always keep two chantiers apart."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    na, nb = {t for t in ta if re.search(r"\d", t)}, {t for t in tb if re.search(r"\d", t)}
    if na and nb and not (na <= nb or nb <= na):
        return 0.0
    ratio = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    sa, sb = set(ta), set(tb)
    small = min(len(sa), len(sb))
    contained = len(sa & sb) / small if small >= 3 else 0.0
    return max(ratio, contained)


def validate(conn, result: dict, from_seq: int, to_seq: int) -> None:
    """Raise ValueError on anything that must fail the reading (it is then retried once by llm.read)."""
    if not isinstance(result.get("cards", []), list) or not isinstance(result.get("approvals", []), list):
        raise ValueError("cards/approvals must be lists")
    modules = known_modules()
    refs = {r["ref"] for r in conn.execute("select ref from devboard.cards")}
    anchors = {r["anchor"] for r in conn.execute("select anchor from devboard.decisions")}
    for c in result.get("cards", []):
        if c.get("ref") and c["ref"] not in refs:
            raise ValueError(f"unknown card {c['ref']}")
        if c.get("module") and c["module"] not in modules:
            raise ValueError(f"unknown module {c['module']}; allowed: {', '.join(sorted(modules))}")
        if c.get("status") not in STATUSES:
            raise ValueError(f"bad status {c.get('status')}")
        if not (c.get("title") or "").strip():
            raise ValueError("card without title")
        for a in c.get("decisions") or []:
            if a not in anchors:
                raise ValueError(f"unknown decision anchor {a}")
        if c.get("deadline"):
            date.fromisoformat(c["deadline"])
    for a in result.get("approvals", []):
        if a.get("ref") not in refs:
            raise ValueError(f"unknown card {a.get('ref')} in approvals")


def _evidence_ok(evidence, lo: int, hi: int) -> list[dict]:
    ev = [e for e in evidence or [] if isinstance(e, dict) and isinstance(e.get("seq"), int)
          and (e.get("quote") or "").strip()]
    if not ev or any(not lo <= e["seq"] <= hi for e in ev):
        return []
    return ev


def _corrected(conn, card_id: int) -> set:
    return {r["field"] for r in conn.execute("select distinct field from devboard.corrections where card_id = %s",
                                             (card_id,))}


def _match(conn, c: dict):
    if c.get("ref"):
        return conn.execute("select * from devboard.cards where ref = %s", (c["ref"],)).fetchone()
    best, score = None, 0.0
    for row in conn.execute("select * from devboard.cards where module is not distinct from %s", (c.get("module"),)):
        s = similarity(row["title"], c["title"])
        if s > score:
            best, score = row, s
    return best if score >= MERGE_AT else None


def _owner(value):
    return value if value in OWNERS else None


def apply(conn, session_id: str, from_seq: int, to_seq: int, result: dict, *, at: datetime | None = None) -> list[str]:
    validate(conn, result, from_seq, to_seq)
    at = at or datetime.now(timezone.utc)
    src = f"{session_id}#{from_seq}-{to_seq}"
    kind = "task" if session_id.startswith("task:") else "session"
    touched: list[str] = []
    for c in result.get("cards", []):
        ev = _evidence_ok(c.get("evidence"), from_seq, to_seq)
        if not ev:
            continue
        values = {"title": c["title"].strip()[:200], "module": c.get("module"), "status": c["status"],
                  "owner": _owner(c.get("owner")), "change": (c.get("change") or "").strip() or None,
                  "deadline": c.get("deadline") or None}
        row = _match(conn, c)
        if row is None:
            row = conn.execute("""insert into devboard.cards (title, module, status, owner, change, deadline,
                                     waiting_since, created_at, updated_at, last_activity_at)
                                  values (%(title)s, %(module)s, %(status)s, %(owner)s, %(change)s, %(deadline)s,
                                          case when %(status)s = 'waiting_owner' then %(at)s end, %(at)s, now(), %(at)s)
                                  returning *""", {**values, "at": at}).fetchone()
            what = "créée"
        else:
            locked = _corrected(conn, row["id"])
            # A matched card keeps its first title unless the reading named it by ref.
            keep = locked | ({"title"} if not c.get("ref") else set())
            new = {k: v for k, v in values.items() if k not in keep and v is not None and v != row[k]}
            if new.get("deadline") is not None and str(row["deadline"]) == str(new["deadline"]):
                new.pop("deadline")
            row = _update(conn, row, new, at)
            what = ("mise à jour : " + ", ".join(sorted(new))) if new else "citée"
        for e in ev:
            conn.execute("""insert into devboard.card_evidence (card_id, kind, source_ref, seq, quote, at)
                            values (%s, %s, %s, %s, %s, %s)""",
                         (row["id"], kind, session_id, e["seq"], e["quote"].strip()[:400], at))
        for kind, targets in (("decision", c.get("decisions")), ("file", c.get("files")), ("blocks", c.get("blocks"))):
            for t in targets or []:
                if kind == "blocks" and not conn.execute("select 1 from devboard.cards where ref = %s", (t,)).fetchone():
                    continue
                conn.execute("""insert into devboard.card_links (card_id, kind, target) values (%s, %s, %s)
                                on conflict do nothing""", (row["id"], kind, str(t)[:500]))
        _activity(conn, row, src, what, at)
        touched.append(row["ref"])
    for a in result.get("approvals", []):
        row = conn.execute("select * from devboard.cards where ref = %s", (a["ref"],)).fetchone()
        if (row["status"] != "waiting_owner" or "status" in _corrected(conn, row["id"])
                or not _evidence_ok([a], from_seq, to_seq)):
            continue
        row = _update(conn, row, {"status": "in_progress"}, at)
        conn.execute("""insert into devboard.card_evidence (card_id, kind, source_ref, seq, quote, at)
                        values (%s, 'session', %s, %s, %s, %s)""",
                     (row["id"], session_id, a["seq"], a["quote"].strip()[:400], at))
        _activity(conn, row, src + "#ok", "accord donné", at)
        if row["ref"] not in touched:
            touched.append(row["ref"])
    if touched:
        db.notify(conn, "cards", refs=touched)
    return touched


def _update(conn, row, new: dict, at: datetime):
    sets = dict(new)
    if "status" in new:
        sets["waiting_since"] = at if new["status"] == "waiting_owner" else None
    cols = ", ".join(f"{k} = %({k})s" for k in sets)
    return conn.execute(f"""update devboard.cards set {cols + ',' if cols else ''} updated_at = now(),
                              last_activity_at = greatest(last_activity_at, %(at)s)
                            where id = %(id)s returning *""", {**sets, "at": at, "id": row["id"]}).fetchone()


def _activity(conn, row, src: str, what: str, at: datetime) -> None:
    conn.execute("""insert into devboard.activity (at, kind, source_ref, card_id, text)
                    values (%s, 'reading', %s, %s, %s) on conflict (kind, source_ref, card_id) do nothing""",
                 (at, src, row["id"], f"{row['ref']} {what}"))


def flags(conn, card: dict, today: date, *, stale_days: int = 7) -> dict:
    open_ = card["status"] not in ("done", "abandoned")
    late = bool(open_ and card["status"] != "waiting_owner" and card.get("deadline") and card["deadline"] < today)
    waiting = None
    if card["status"] == "waiting_owner" and card.get("waiting_since"):
        waiting = (today - card["waiting_since"].date()).days
    last = card.get("last_activity_at")
    stale = bool(card["status"] == "in_progress" and last and last.date() < today - timedelta(days=stale_days))
    return {"late": late, "waiting_days": waiting, "stale": stale}
