"""Owner corrections. A correction is applied at once, recorded in devboard.corrections, and from then on no reading
can overwrite that field of that card (cards.apply skips corrected fields)."""
from __future__ import annotations

import json
from datetime import date

from . import cards, db

FIELDS = ("status", "title", "module", "owner", "change", "deadline", "decision_link")


def _value(conn, field: str, value):
    if field == "status":
        if value not in cards.STATUSES:
            raise ValueError(f"status: one of {', '.join(cards.STATUSES)}")
    elif field == "owner":
        if value not in cards.OWNERS:
            raise ValueError(f"owner: one of {', '.join(cards.OWNERS)}")
    elif field == "module":
        if value in ("", None):
            return None
        if value not in cards.known_modules():
            raise ValueError(f"unknown module {value}")
    elif field == "deadline":
        if value in ("", None):
            return None
        date.fromisoformat(str(value))
    elif field == "decision_link":
        if not conn.execute("select 1 from devboard.decisions where anchor = %s", (value,)).fetchone():
            raise ValueError(f"unknown decision anchor {value}")
    elif field in ("title", "change"):
        value = str(value or "").strip()
        if field == "title" and not value:
            raise ValueError("empty title")
    return value


def correct(conn, spec: dict) -> dict:
    ref, field = spec.get("ref"), spec.get("field")
    card = conn.execute("select * from devboard.cards where ref = %s", (ref,)).fetchone()
    if card is None:
        raise ValueError(f"unknown card {ref}")
    if field not in FIELDS:
        raise ValueError(f"field: one of {', '.join(FIELDS)}")
    value = _value(conn, field, spec.get("value"))
    reason = str(spec.get("reason") or "").strip()[:500]
    by = str(spec.get("by") or "owner")[:40]
    cid = conn.execute("""insert into devboard.corrections (card_id, field, value, reason, by)
                          values (%s, %s, %s, %s, %s) returning id""",
                       (card["id"], field, json.dumps(value), reason, by)).fetchone()["id"]
    if field == "decision_link":
        conn.execute("""insert into devboard.card_links (card_id, kind, target) values (%s, 'decision', %s)
                        on conflict do nothing""", (card["id"], value))
    else:
        extra = ""
        if field == "status":
            extra = ", waiting_since = case when %(v)s = 'waiting_owner' then now() end"
        conn.execute(f"update devboard.cards set {field} = %(v)s{extra}, updated_at = now(), "
                     f"last_activity_at = now() where id = %(id)s", {"v": value, "id": card["id"]})
    conn.execute("""insert into devboard.activity (kind, source_ref, card_id, text)
                    values ('correction', %s, %s, %s)""",
                 (f"correction:{cid}", card["id"], f"{ref} corrigé : {field} → {value}" + (f" ({reason})" if reason else "")))
    db.notify(conn, "cards", refs=[ref])
    return {"ok": True, "ref": ref, "field": field, "value": value, "correction": cid}
