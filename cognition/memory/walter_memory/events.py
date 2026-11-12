"""Canonical event store: record (idempotent, validated, append-only) and read."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from . import privacy, types
from .logs import vault_scrub
from .db import connection

ACTOR_FIELDS = ("account", "external_id", "display_name", "handles", "phones", "emails", "is_self", "attributes")
_identity_cache: dict[tuple[str, str, str], str] = {}
_partitions: set[str] = set()


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):  # epoch seconds or milliseconds
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def upsert_identity(conn, source: str, actor: dict) -> str:
    """Record the actor as the source knows it (A4). Returns identity_id; no entity resolution here."""
    key = (source, actor.get("account") or "", str(actor["external_id"]))
    if key in _identity_cache and not actor.get("display_name"):
        return _identity_cache[key]
    row = conn.execute(
        """insert into core.source_identities (source, account, external_id, display_name, handles, phones, emails,
                                              is_self, attributes)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (source, account, external_id) do update set
             display_name = coalesce(excluded.display_name, core.source_identities.display_name),
             handles = core.source_identities.handles || excluded.handles,
             phones = coalesce((select array_agg(distinct p) from unnest(core.source_identities.phones || excluded.phones) p), '{}'),
             emails = coalesce((select array_agg(distinct e) from unnest(core.source_identities.emails || excluded.emails) e), '{}'),
             is_self = core.source_identities.is_self or excluded.is_self,
             last_seen = now()
           returning identity_id""",
        (key[0], key[1], key[2], actor.get("display_name"), json.dumps(actor.get("handles") or {}),
         actor.get("phones") or [], actor.get("emails") or [], bool(actor.get("is_self")),
         json.dumps(actor.get("attributes") or {}))).fetchone()
    _identity_cache[key] = str(row["identity_id"])
    return _identity_cache[key]


def _ensure_partitions(conn, months: Iterable[datetime]) -> None:
    for ts in months:
        name = f"events_{ts:%Y_%m}"
        if name not in _partitions:
            conn.execute("select core.ensure_event_partition(%s)", (ts,))
            _partitions.add(name)


def record_events(events: list[dict], *, conn=None) -> dict:
    """Write a batch of observed events. Idempotent on (source, source_id, event_type).

    Each event: event_type, source, source_id, occurred_at, and optionally source_account, content, payload,
    thread_id, reply_to, object_refs, privacy_class, actor ({external_id, account, display_name, ...}) or
    actor_identity_id. Returns {"inserted": n, "duplicates": n, "event_ids": [...] (inserted only)}.
    """
    if conn is None:
        with connection() as c:
            return record_events(events, conn=c)
    prepared = []
    for e in events:
        payload = e.get("payload") or {}
        version = types.validate(e["event_type"], payload)
        occurred = _ts(e["occurred_at"])
        content = vault_scrub(e.get("content"))     # a vault value pasted in a message never enters history
        if content and "\x00" in content:          # PostgreSQL text/jsonb cannot hold NUL
            content = content.replace("\x00", "\ufffd")
        actor_id = e.get("actor_identity_id")
        if not actor_id and e.get("actor"):
            actor_id = upsert_identity(conn, e["source"], e["actor"])
        prepared.append({
            "event_id": str(e.get("event_id") or uuid.uuid4()), "event_type": e["event_type"], "type_version": version,
            "source": e["source"], "source_account": e.get("source_account") or "", "source_id": str(e["source_id"]),
            "occurred_at": occurred, "actor_identity_id": actor_id, "thread_id": e.get("thread_id"),
            "reply_to": e.get("reply_to"), "content": content,
            "content_hash": hashlib.sha256(content.encode()).hexdigest() if content else None,
            "object_refs": [str(o) for o in e.get("object_refs") or []],
            "payload": vault_scrub(json.dumps(payload, default=str)).replace("\\u0000", "\\ufffd"),
            "privacy_class": e.get("privacy_class") or privacy.classify_event(conn, e),
        })
    _ensure_partitions(conn, {p["occurred_at"].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                              for p in prepared})
    inserted = []
    with conn.cursor() as cur:
        for p in prepared:
            cur.execute(
                """with k as (
                     insert into core.event_keys (source, source_id, event_type, event_id, occurred_at)
                     values (%(source)s, %(source_id)s, %(event_type)s, %(event_id)s, %(occurred_at)s)
                     on conflict do nothing returning event_id)
                   insert into core.events (event_id, event_type, type_version, source, source_account, source_id,
                       occurred_at, actor_identity_id, thread_id, reply_to, content, content_hash, object_refs,
                       payload, privacy_class)
                   select k.event_id, %(event_type)s, %(type_version)s, %(source)s, %(source_account)s, %(source_id)s,
                       %(occurred_at)s, %(actor_identity_id)s, %(thread_id)s, %(reply_to)s, %(content)s,
                       %(content_hash)s, %(object_refs)s::uuid[], %(payload)s::jsonb, %(privacy_class)s from k
                   returning event_id""", p)
            row = cur.fetchone()
            if row:
                inserted.append(str(row["event_id"]))
    return {"inserted": len(inserted), "duplicates": len(prepared) - len(inserted), "event_ids": inserted}


def record_event(**event) -> dict:
    return record_events([event])


def get_events(*, source: str | None = None, event_types: list[str] | None = None, thread_id: str | None = None,
               actor_identity_id: str | None = None, since: Any = None, until: Any = None, text: str | None = None,
               limit: int = 50, include_retracted: bool = False, max_privacy: str = "local_only",
               order: str = "desc", event_id: str | None = None) -> list[dict]:
    """Read events newest first (order="asc": oldest first, e.g. « the first event about X »). Retracted events are
    hidden unless include_retracted. max_privacy: 'cloud_allowed' returns only cloud_allowed rows (for callers that
    will ship them to a cloud model)."""
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    where, args = [], []
    if event_id:
        where.append("e.event_id = %s::uuid"); args.append(event_id)
    if source:
        where.append("e.source = %s"); args.append(source)
    if event_types:
        where.append("e.event_type = any(%s)"); args.append(event_types)
    if thread_id:
        where.append("e.thread_id = %s"); args.append(thread_id)
    if actor_identity_id:
        where.append("e.actor_identity_id = %s"); args.append(actor_identity_id)
    if since:
        where.append("e.occurred_at >= %s"); args.append(_ts(since))
    if until:
        where.append("e.occurred_at < %s"); args.append(_ts(until))
    if text:
        where.append("e.content ilike %s"); args.append(f"%{text}%")
    allowed = privacy.allowed_classes(max_privacy)
    where.append("e.privacy_class = any(%s)"); args.append(allowed)
    if not include_retracted:
        where.append("""not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                        and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))""")
    sql = f"""select e.event_id::text, e.event_type, e.source, e.source_account, e.source_id, e.occurred_at,
                     e.thread_id, e.reply_to, e.content, e.payload, e.object_refs, e.privacy_class,
                     i.display_name as actor_name, i.is_self as actor_is_self
              from core.events e left join core.source_identities i on i.identity_id = e.actor_identity_id
              {'where ' + ' and '.join(where) if where else ''}
              order by e.occurred_at {order}, e.event_id {order} limit %s"""
    with connection() as conn:
        rows = conn.execute(sql, (*args, int(limit))).fetchall()
        if event_id and rows:     # one event in full: its files and their derived text too (A5)
            atts = attachments(rows, max_privacy=max_privacy, chars=4000, conn=conn)
            for r in rows:
                r["attachments"] = atts.get(r["event_id"], [])
        return rows


# ───────────────────────────── attachments (A5, 2026-11-11) ─────────────────────────────
# A message's files are resolved at read time through core.object_links (the connectors link each stored file to its
# message) and core.events.object_refs, so the whole history shows its attachments without rewriting append-only rows.
EVENT_LINKS = {"beeper": ("beeper_message", ""), "gmail": ("email", "gmail:")}   # source → (link type, id prefix)
THREAD_LINKS = {"hermes": "hermes_session"}                                       # files linked to a whole thread
ATTACHMENT_CHARS = 300
_KIND_LABEL = {"transcript": "transcript", "extract": "text", "ocr": "ocr", "caption": "caption"}


def link_target(source: str | None, source_id: str | None) -> tuple[str, str] | None:
    """The core.object_links target of a message event, or None when its source links no files per message."""
    if source not in EVENT_LINKS or not source_id:
        return None
    kind, prefix = EVENT_LINKS[source]
    return kind, prefix + str(source_id)


def link_sql(alias: str = "e") -> str:
    """SQL condition joining core.object_links `l` to the events `alias` (per-message links)."""
    return " or ".join(f"({alias}.source = '{s}' and l.target_type = '{t}' and l.target_id = '{p}' || {alias}.source_id)"
                       for s, (t, p) in EVENT_LINKS.items())


def _attachment(o: dict, chars: int, allowed: list[str]) -> dict:
    if o["privacy_class"] not in allowed:
        return {"object_id": o["id"], "kind": o["kind"], "withheld": "privacy"}
    text = o.get("derived_text")
    media = (o.get("meta") or {}).get("media") or {}
    return {"object_id": o["id"], "kind": o["kind"], "mime": o.get("mime"), "name": o.get("original_name"),
            "derived_kind": o.get("derived_kind"),
            "text": None if text is None else (text[:chars] + ("…" if len(text) > chars else "")),
            **({"note": media.get("reason") or media.get("result")} if text == "" and media else {})}


def attachments(rows: list[dict], *, max_privacy: str = "cloud_allowed", chars: int = ATTACHMENT_CHARS,
                conn=None) -> dict[str, list[dict]]:
    """event_id → [{object_id, kind, mime, name, derived_kind, text (bounded)}] for these event rows (they need
    event_id, source, source_id and optionally object_refs). Objects the reader may not see keep only id and kind.
    No query when no row can carry files."""
    keys: dict[tuple[str, str], list[str]] = {}
    refs: dict[str, list[str]] = {}
    for r in rows:
        t = link_target(r.get("source"), r.get("source_id"))
        if t:
            keys.setdefault(t, []).append(str(r["event_id"]))
        for o in r.get("object_refs") or []:
            refs.setdefault(str(o), []).append(str(r["event_id"]))
    if not keys and not refs:
        return {}
    if conn is None:
        with connection() as c:
            return attachments(rows, max_privacy=max_privacy, chars=chars, conn=c)
    found = conn.execute(
        """select l.target_type, l.target_id, null::text as ref, o.id::text as id, o.kind, o.mime, o.original_name,
                  o.derived_kind, o.derived_text, o.privacy_class, o.meta, o.captured_at
           from core.object_links l join core.objects o on o.id = l.object_id
           where (l.target_type, l.target_id) in (select * from unnest(%s::text[], %s::text[])) and o.purged_at is null
           union all
           select null, null, o.id::text, o.id::text, o.kind, o.mime, o.original_name, o.derived_kind, o.derived_text,
                  o.privacy_class, o.meta, o.captured_at
           from core.objects o where o.id = any(%s::uuid[]) and o.purged_at is null
           order by captured_at nulls last, id""",
        ([k[0] for k in keys], [k[1] for k in keys], list(refs))).fetchall()
    allowed = privacy.allowed_classes(max_privacy)
    out: dict[str, list[dict]] = {}
    for o in found:
        owners = keys.get((o["target_type"], o["target_id"]), []) if o["ref"] is None else refs.get(o["ref"], [])
        for eid in owners:
            lst = out.setdefault(eid, [])
            if all(a["object_id"] != o["id"] for a in lst):
                lst.append(_attachment(o, chars, allowed))
    return out


def attachment_line(a: dict) -> str:
    """One attachment as a model reads it: [audio · object <id> · transcript: "…"]."""
    head = f"[{a.get('kind') or 'file'} · object {a['object_id']}"
    if a.get("withheld"):
        return head + " · not readable here]"
    if a.get("text") is None:
        return head + (f" · {a['name']}" if a.get("name") else "") + " · no text yet]"
    if a["text"] == "":
        return head + f" · {a.get('note') or 'no text'}]"
    label = _KIND_LABEL.get(a.get("derived_kind") or "", "text")
    return head + f' · {label}: "' + a["text"].replace("\n", " ") + '"]'


def render_message(row: dict, atts: list[dict] | None = None) -> str:
    """A message's text followed by one line per attachment (for any renderer of a conversation): pass the row and
    `attachments([rows])[event_id]`, or use render_messages."""
    parts = [row.get("content") or ""] + [attachment_line(a) for a in atts or []]
    return "\n".join(p for p in parts if p)


def render_messages(rows: list[dict], *, max_privacy: str = "cloud_allowed", chars: int = ATTACHMENT_CHARS) -> list[str]:
    """Each row's text with its attachment lines (one query for all rows); never raises (text only on error)."""
    try:
        atts = attachments(rows, max_privacy=max_privacy, chars=chars)
    except Exception:  # noqa: BLE001
        atts = {}
    return [render_message(r, atts.get(str(r.get("event_id")))) for r in rows]


def compact(rows: list[dict], text: str | None = None, width: int = 500, budget: int = 16000, *,
            max_privacy: str = "cloud_allowed") -> dict:
    """Events as an agent reads them: no payload, the content cut to a window around the searched text, the whole
    answer bounded. One full event = get_events(event_id=…). A 50-event answer used to be ~56K chars: spilled to a
    file, then grepped, then searched again (11 steps for « the first event about Sagora », 07/11).
    Each message carries its files (`attachments`, with their derived text, bounded) — A5."""
    out, used, low = [], 0, (text or "").lower()
    try:
        atts = attachments(rows, max_privacy=max_privacy)
    except Exception:  # noqa: BLE001 — attachments enrich the answer, never break it
        atts = {}
    for r in rows:
        content = r.get("content") or ""
        i = content.lower().find(low) if low else -1
        start = max(0, i - width // 3) if i > 0 else 0
        snippet = ("…" if start else "") + content[start:start + width] + ("…" if start + width < len(content) else "")
        item = {"event_id": r["event_id"], "occurred_at": str(r["occurred_at"]), "source": r["source"],
                "event_type": r["event_type"], "thread_id": r.get("thread_id"), "source_id": r.get("source_id"),
                "actor": r.get("actor_name"), "chars": len(content), "content": snippet}
        if atts.get(str(r["event_id"])):
            item["attachments"] = atts[str(r["event_id"])]
        size = len(json.dumps(item, ensure_ascii=False, default=str))
        if out and used + size > budget:
            break
        out.append(item); used += size
    more = len(rows) - len(out)
    return {"events": out, "truncated": more,
            **({"hint": f"{more} more not shown: narrow with since/until, or read one event in full by event_id"}
               if more else {})}


def stats() -> list[dict]:
    with connection() as conn:
        return conn.execute("""select source, event_type, count(*) as n, min(occurred_at) as first, max(occurred_at) as last
                               from core.events group by 1, 2 order by 1, 2""").fetchall()
