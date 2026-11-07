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
               limit: int = 50, include_retracted: bool = False, max_privacy: str = "local_only") -> list[dict]:
    """Read events newest first. Retracted events are hidden unless include_retracted.
    max_privacy: 'cloud_allowed' returns only cloud_allowed rows (for callers that will ship them to a cloud model)."""
    where, args = [], []
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
              order by e.occurred_at desc limit %s"""
    with connection() as conn:
        return conn.execute(sql, (*args, int(limit))).fetchall()


def stats() -> list[dict]:
    with connection() as conn:
        return conn.execute("""select source, event_type, count(*) as n, min(occurred_at) as first, max(occurred_at) as last
                               from core.events group by 1, 2 order by 1, 2""").fetchall()
