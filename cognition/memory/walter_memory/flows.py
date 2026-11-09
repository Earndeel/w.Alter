"""Deterministic flows (Memory V1 P1.4): the raw streams turned into dated observations, without any model call.

  visits         GPS samples (Overland, local_only) → stays: points within RADIUS_M of the running centre (or on the
                 same Wi-Fi network) for at least MIN_STAY; each stay belongs to a place entity (local_only: its
                 coordinates and its name — the Wi-Fi network — never leave the VM); the place where the nights are
                 spent is marked as the probable home. Nothing is geocoded, nothing is interpreted by a cloud service.
  conversations  messages of a chat (Beeper, Gmail) grouped into bursts (a gap over BURST_GAP opens a new one):
                 who, how many, when — the class of the burst is the strictest of its messages
  appointments   personal calendar events (holiday and week-number calendars excluded): planned, not attended; the
                 latest version of a calendar event wins, a cancelled one is retracted
  work_sessions  the owner's conversations with W.Alter's agents, per thread and local day, with their subject
All are V1 knowledge (core.derived_items, generation g1, epistemic observed, derived_by flows.*), upserted by a
stable ref and written only when they changed: recomputing gives the same rows and writes nothing.

Event-driven (2026-11-03): assimilation.py recomputes only what a new canonical event touches — one chat thread
(`conversations(thread=…)`), one calendar event (`appointments(calendar_event=…)`), one agent thread
(`work_sessions(thread=…)`), the GPS time range (`visits(since, until)`). A burst is always computed from its true
start (the thread is read back to the last gap), so a late message merges or splits bursts correctly and the bursts
that no longer exist are retracted. The window functions without a key are the reconciliation pass.
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import organic, privacy
from .db import connection

log = logging.getLogger("walter.flows")
RADIUS_M, MIN_STAY, MAX_GAP = 80.0, timedelta(minutes=10), timedelta(hours=3)
PLACE_RADIUS_M = 150.0
BURST_GAP = timedelta(minutes=45)
RUNTIMES = ("hermes", "claude_code", "codex", "dsh")
CHAT_SOURCES = ("beeper", "gmail")
CHAT_TYPES = ("message.sent", "message.received", "email.sent", "email.received")
NOISE_CALENDARS = ("#holiday@", "#weeknum@", "#contacts@")


def tz() -> ZoneInfo:
    return ZoneInfo(organic.settings().get("periods", {}).get("tz", "Asia/Bangkok"))


def _m(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _upsert(conn, *, kind: str, builder: str, ref: str, content: str, attributes: dict, event_ids: list[str],
            privacy_class: str, at: datetime, entities: list[str] | None = None, changed: list | None = None) -> str:
    """One V1 observation per (builder, ref). Written only when it differs from what is stored (2026-11-03): an
    unchanged recomputation writes nothing, so it publishes nothing on the bus and wakes nothing downstream. The builder
    owns the whole row: no other processor keeps its state in it (processing.* holds processing state)."""
    attrs = json.loads(json.dumps(attributes, ensure_ascii=False, default=str))
    ids, ents = [str(e) for e in event_ids], [str(e) for e in entities or []]
    row = conn.execute("""select item_id::text, privacy_class, content, attributes, status, valid_from,
                                 source_event_ids::text[] ev, subject_entity_ids::text[] ent
                          from core.derived_items where derived_by = %s and source_refs->>'ref' = %s""",
                       (builder, ref)).fetchone()
    cls = privacy.strictest(privacy_class, row["privacy_class"]) if row else privacy_class
    if row:
        if (row["content"], row["attributes"], row["status"], row["valid_from"], row["ev"], row["ent"], row["privacy_class"]) \
                != (content, attrs, "derived", at, ids, ents, cls):
            conn.execute("""update core.derived_items set content = %s, attributes = %s, source_event_ids = %s::uuid[],
                              privacy_class = %s, valid_from = %s, status = 'derived', subject_entity_ids = %s::uuid[]
                            where item_id = %s""", (content, json.dumps(attrs, ensure_ascii=False), ids, cls, at, ents,
                                                    row["item_id"]))
            if changed is not None:
                changed.append(row["item_id"])
        return row["item_id"]
    iid = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                              source_event_ids, source_refs, valid_from, confidence, privacy_class, generation, epistemic,
                              stage, scope, subject_entity_ids)
                          values (%s, %s, %s, 'derived', %s, '1', %s::uuid[], %s, %s, 1.0, %s, 'g1', 'observed', 'stated',
                                  'durable', %s::uuid[]) returning item_id::text""",
                       (kind, content, json.dumps(attrs, ensure_ascii=False), builder, ids,
                        json.dumps({"ref": ref}), at, cls, ents)).fetchone()["item_id"]
    if changed is not None:
        changed.append(iid)
    return iid


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def _retract_missing(conn, builder: str, since: datetime, until: datetime, keep: set[str],
                     ref_prefix: str | None = None, reason: str = "not found again on rebuild",
                     except_prefix: str | None = None) -> int:
    rows = conn.execute("""update core.derived_items set status = 'retracted',
                               attributes = attributes || jsonb_build_object('retracted_reason', %s::text)
                           where derived_by = %s and generation = 'g1' and status = 'derived'
                             and valid_from >= %s and valid_from < %s and not (item_id = any(%s::uuid[]))
                             and (%s::text is null or source_refs->>'ref' like %s)
                             and (%s::text is null or source_refs->>'ref' not like %s)
                           returning item_id::text""",
                        (reason, builder, since, until, list(keep), ref_prefix, _like(ref_prefix or ""),
                         except_prefix, _like(except_prefix or ""))).fetchall()
    return len(rows)


def _retract_ref(conn, builder: str, ref: str, reason: str) -> int:
    rows = conn.execute("""update core.derived_items set status = 'retracted',
                               attributes = attributes || jsonb_build_object('retracted_reason', %s::text)
                           where derived_by = %s and source_refs->>'ref' = %s and status = 'derived'
                           returning 1""", (reason, builder, ref)).fetchall()
    return len(rows)


def _hm(t: datetime, z: ZoneInfo) -> str:
    return t.astimezone(z).strftime("%H:%M")


def _span(a: datetime, b: datetime, z: ZoneInfo) -> str:
    la, lb = a.astimezone(z), b.astimezone(z)
    if la.date() == lb.date():
        return f"le {la:%d/%m} de {la:%H:%M} à {lb:%H:%M}"
    return f"du {la:%d/%m %H:%M} au {lb:%d/%m %H:%M}"


def _dur(d: timedelta) -> str:
    m = int(d.total_seconds() // 60)
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


# ───────────────────────────── visits (GPS, local only) ─────────────────────────────
def stays(samples: list[dict]) -> list[dict]:
    """Samples (time order) → stays of at least MIN_STAY within RADIUS_M of their centre or on one Wi-Fi network."""
    out, cur = [], None

    def close():
        if cur and cur["end"] - cur["start"] >= MIN_STAY:
            d = sorted(_m(cur["centre"], (p["lat"], p["lng"])) for p in cur["pts"])
            cur["radius_m"] = round(d[int(0.9 * (len(d) - 1))], 1)
            cur["wifi"] = Counter(p["wifi"] for p in cur["pts"] if p["wifi"]).most_common(1)[0][0] \
                if any(p["wifi"] for p in cur["pts"]) else None
            out.append(cur)

    for p in samples:
        if p["accuracy"] and p["accuracy"] > 200:
            continue
        here = (p["lat"], p["lng"])
        if cur and p["at"] - cur["end"] <= MAX_GAP and (
                _m(cur["centre"], here) <= RADIUS_M + min(p["accuracy"] or 0, 60) or (p["wifi"] and p["wifi"] in cur["wifis"])):
            n = len(cur["pts"])
            cur["centre"] = ((cur["centre"][0] * n + here[0]) / (n + 1), (cur["centre"][1] * n + here[1]) / (n + 1))
            cur["pts"].append(p); cur["end"] = p["at"]
            if p["wifi"]:
                cur["wifis"].add(p["wifi"])
            continue
        close()
        cur = {"start": p["at"], "end": p["at"], "centre": here, "pts": [p], "wifis": {p["wifi"]} if p["wifi"] else set()}
    close()
    return out


def _place(conn, stay: dict) -> str:
    from . import entities
    rows = conn.execute("""select entity_id::text, attributes from core.entities where entity_type = 'place'
                           and status = 'active' and privacy_class = 'local_only'""").fetchall()
    for r in rows:
        a = r["attributes"] or {}
        if (stay["wifi"] and stay["wifi"] in (a.get("wifis") or [])) or \
                _m((a["lat"], a["lng"]), stay["centre"]) <= PLACE_RADIUS_M:
            wifis = sorted(set(a.get("wifis") or []) | ({stay["wifi"]} if stay["wifi"] else set()))
            if wifis != sorted(a.get("wifis") or []):
                conn.execute("update core.entities set attributes = attributes || %s, updated_at = now() where entity_id = %s",
                             (json.dumps({"wifis": wifis}), r["entity_id"]))
            return r["entity_id"]
    name = stay["wifi"] or f"Lieu {stay['centre'][0]:.4f}, {stay['centre'][1]:.4f}"
    return entities.ensure(conn, "place", name, attributes={"lat": round(stay["centre"][0], 6),
                                                            "lng": round(stay["centre"][1], 6), "radius_m": PLACE_RADIUS_M,
                                                            "wifis": [stay["wifi"]] if stay["wifi"] else [],
                                                            "origin": "flows.visits", "confirmed": False},
                           privacy_class="local_only")


def _samples(lo: datetime, hi: datetime) -> list[dict]:
    with connection() as conn:
        rows = conn.execute("""select event_id::text, occurred_at, (payload->>'lat')::float lat, (payload->>'lng')::float lng,
                                      (payload->>'accuracy_m')::float accuracy,
                                      payload->'raw'->'properties'->>'wifi' wifi
                               from core.events e where source = 'overland' and event_type = 'location.sample'
                                 and occurred_at >= %s and occurred_at < %s and payload ? 'lat'
                                 and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                                                 and r.source = 'overland'
                                                 and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
                               order by occurred_at""", (lo, hi)).fetchall()
    return [{"id": r["event_id"], "at": r["occurred_at"], "lat": r["lat"], "lng": r["lng"],
             "accuracy": r["accuracy"], "wifi": (r["wifi"] or "").strip() or None} for r in rows]


def visits(since: datetime | None = None, until: datetime | None = None) -> dict:
    """Stays from the samples of [since, until), read back to the true start of the stay in progress at `since` (a long
    stay cut by the window edge would otherwise be restated with a later start at every pass — a new row each time).
    Every stay computed from complete samples is stated (unchanged ones are not rewritten); a stay of that span that no
    longer exists (a late or retracted sample changed it, or a former truncated copy) is retracted."""
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=2), until or now
    z = tz()
    lo = since - MAX_GAP
    for _ in range(14):        # extend backwards while the first stay may have begun before the samples read
        samples = _samples(lo, until + MAX_GAP)
        found = stays(samples)
        if not found or found[0]["start"] > samples[0]["at"] or samples[0]["at"] - lo > MAX_GAP:
            break
        lo -= timedelta(days=1)
    span_lo = found[0]["start"] if found else since
    keep, changed = set(), []
    from . import entities
    with connection() as conn:
        me = entities.owner_id(conn)
        for s in found:
            if s["start"] >= until:
                continue
            place = _place(conn, s)
            pname = conn.execute("select canonical_name from core.entities where entity_id = %s", (place,)).fetchone()["canonical_name"]
            ids = [p["id"] for p in s["pts"]]
            sample_ids = ids if len(ids) <= 60 else [ids[int(k * (len(ids) - 1) / 59)] for k in range(60)]
            attrs = {"start": s["start"], "end": s["end"], "lat": round(s["centre"][0], 6), "lng": round(s["centre"][1], 6),
                     "radius_m": s["radius_m"], "points": len(ids), "wifi": s["wifi"], "place_id": place, "tz": str(z)}
            n = len(changed)
            iid = _upsert(conn, kind="visit", builder="flows.visits", ref=f"visit:{s['start'].isoformat()}",
                          content=f"Présence à « {pname} » {_span(s['start'], s['end'], z)} ({_dur(s['end'] - s['start'])})",
                          attributes=attrs, event_ids=sample_ids, privacy_class="local_only", at=s["start"],
                          entities=[place], changed=changed)
            keep.add(iid)
            if me and len(changed) > n:
                entities.relate(conn, me, "visited", place, sample_ids[:5], "local_only", s["start"], derived_by="flows.visits")
        retracted = _retract_missing(conn, "flows.visits", min(span_lo, since), until - MIN_STAY, keep,
                                     reason="stay changed (late, retracted or truncated samples)")
        homes = mark_home(conn)
    return {"samples": len(samples), "visits": len(keep), "changed": len(changed), "retracted": retracted, "home": homes}


def mark_home(conn) -> int:
    """The place with the most local night hours (00:00-06:00) over its visits is the probable home (written only
    when it changes)."""
    z = tz()
    rows = conn.execute("""select attributes from core.derived_items where derived_by = 'flows.visits' and status = 'derived'
                           and valid_from > now() - interval '30 days'""").fetchall()
    nights = Counter()
    for r in rows:
        a = r["attributes"]
        s, e = datetime.fromisoformat(a["start"]), datetime.fromisoformat(a["end"])
        t = s
        while t < e:
            if 0 <= t.astimezone(z).hour < 6:
                nights[a["place_id"]] += 1
            t += timedelta(minutes=30)
    if not nights:
        return 0
    home = nights.most_common(1)[0][0]
    cur = [r["entity_id"] for r in conn.execute("""select entity_id::text from core.entities
                                                   where entity_type = 'place' and attributes ? 'home'""")]
    if cur == [home]:
        return 0
    conn.execute("""update core.entities set attributes = attributes - 'home' where entity_type = 'place'
                    and attributes ? 'home' and entity_id <> %s""", (home,))
    conn.execute("""update core.entities set attributes = attributes || '{"home": true}' where entity_id = %s""", (home,))
    return 1


# ───────────────────────────── conversations (Beeper, Gmail) ─────────────────────────────
def _burst_start(conn, src: str, thread: str, at: datetime) -> datetime:
    """The first message of the burst that contains `at`: read the thread backwards until a gap over BURST_GAP."""
    start = at
    while True:
        prev = conn.execute("""select max(occurred_at) t from core.events
                               where source = %s and thread_id = %s and event_type = any(%s)
                                 and occurred_at < %s and occurred_at >= %s""",
                            (src, thread, list(CHAT_TYPES), start, start - BURST_GAP)).fetchone()["t"]
        if prev is None:
            return start
        start = prev


def _chat_threads(conn, since: datetime, until: datetime, sources) -> list[tuple[str, str]]:
    return [(r["source"], r["thread_id"]) for r in conn.execute(
        """select distinct source, thread_id from core.events where source = any(%s) and event_type = any(%s)
           and thread_id is not null and occurred_at >= %s and occurred_at < %s""",
        (list(sources), list(CHAT_TYPES), since, until))]


def conversations(since: datetime | None = None, until: datetime | None = None, sources=CHAT_SOURCES,
                  thread: tuple[str, str] | None = None) -> dict:
    """Bursts of the given thread (event-driven: from the burst containing `since`, to now) or of every chat thread
    active in [since, until) (reconciliation). Unchanged bursts are not rewritten; a burst of the recomputed span that no
    longer exists (merged or split by a late message) is retracted."""
    now = datetime.now(timezone.utc)
    since = since or now - timedelta(days=2)
    until = until or now
    z = tz()
    with connection() as conn:
        threads = [thread] if thread else _chat_threads(conn, since, until, sources)
    from . import entities
    out = {"threads": len(threads), "bursts": 0, "changed": 0, "retracted": 0}
    for src, th in threads:
        changed: list = []
        with connection() as conn:
            lo = _burst_start(conn, src, th, since)
            hi = now if thread else until
            msgs = conn.execute("""
                select e.event_id::text, e.source, e.event_type, e.thread_id, e.occurred_at, e.privacy_class,
                       e.actor_identity_id::text actor, coalesce(e.payload->'chat'->>'title', e.payload->>'subject') title,
                       coalesce(e.payload->'chat'->>'network', e.source) network, e.payload->'chat'->>'type' chat_type,
                       l.entity_id::text entity, coalesce(en.canonical_name, i.display_name) who
                from core.events e
                left join core.identity_links l on l.identity_id = e.actor_identity_id and l.status = 'confirmed'
                left join core.entities en on en.entity_id = l.entity_id
                left join core.source_identities i on i.identity_id = e.actor_identity_id
                where e.source = %s and e.thread_id = %s and e.event_type = any(%s)
                  and e.occurred_at >= %s and e.occurred_at <= %s
                  and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                                  and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
                order by e.occurred_at, e.event_id""", (src, th, list(CHAT_TYPES), lo, hi)).fetchall()
            keep: set[str] = set()
            me = entities.owner_id(conn)
            bursts, cur = [], []
            for m in msgs:
                if cur and m["occurred_at"] - cur[-1]["occurred_at"] > BURST_GAP:
                    bursts.append(cur); cur = []
                cur.append(m)
            if cur:
                bursts.append(cur)
            for b in bursts:     # every burst from `lo` is complete (lo is a burst start): all are (re)stated
                owner = sum(1 for m in b if m["event_type"] in ("message.sent", "email.sent"))
                people = {m["entity"]: m["who"] for m in b if m["entity"] and m["entity"] != me and m["entity"]}
                names = [w for w in dict.fromkeys(m["who"] for m in b if m["entity"] != me and m["who"])][:5]
                cls = privacy.strictest(*(m["privacy_class"] for m in b))
                title = b[0]["title"] or ", ".join(names) or th[:12]
                kind_word = "Échange" if src != "gmail" else "Échange de courriels"
                content = (f"{kind_word} {b[0]['network']} « {title} »{' (groupe)' if b[0]['chat_type'] == 'group' else ''} "
                           f"{_span(b[0]['occurred_at'], b[-1]['occurred_at'], z)} : {len(b)} messages dont {owner} de "
                           f"Monsieur" + (f" ; avec {', '.join(names)}" if names else ""))
                attrs = {"start": b[0]["occurred_at"], "end": b[-1]["occurred_at"], "thread": th, "source": src,
                         "network": b[0]["network"], "title": b[0]["title"], "chat_type": b[0]["chat_type"],
                         "messages": len(b), "owner_messages": owner, "participants": list(people), "tz": str(z)}
                n = len(changed)
                iid = _upsert(conn, kind="conversation", builder="flows.conversations",
                              ref=f"conv:{src}:{th}:{b[0]['occurred_at'].isoformat()}", content=content,
                              attributes=attrs, event_ids=[m["event_id"] for m in b][:300], privacy_class=cls,
                              at=b[0]["occurred_at"], entities=list(people)[:20], changed=changed)
                keep.add(iid); out["bursts"] += 1
                if me and owner and len(changed) > n:
                    for eid in list(people)[:20]:
                        entities.relate(conn, me, "exchanged_with", eid, [b[0]["event_id"]], cls, b[0]["occurred_at"],
                                        derived_by="flows.conversations")
            # bursts of this span that no longer exist (merged, split or retracted messages)
            out["retracted"] += _retract_missing(conn, "flows.conversations", lo, hi + timedelta(seconds=1), keep,
                                                 ref_prefix=f"conv:{src}:{th}:", reason="burst changed (late or retracted message)")
        out["changed"] += len(changed)
    return out


# ───────────────────────────── appointments (calendar) ─────────────────────────────
def _when(v: dict | None, default_tz: ZoneInfo) -> datetime | None:
    if not v:
        return None
    if v.get("dateTime"):
        return datetime.fromisoformat(v["dateTime"])
    if v.get("date"):
        return datetime.fromisoformat(v["date"]).replace(tzinfo=default_tz)
    return None


def appointments(since: datetime | None = None, until: datetime | None = None, calendar_event: str | None = None) -> dict:
    """One appointment per calendar event, from its latest version (a moved meeting is updated, a cancelled one or one
    moved to a noise calendar is retracted). `calendar_event` = event-driven, one event; else every event of the window."""
    now = datetime.now(timezone.utc)
    z = tz()
    with connection() as conn:
        if calendar_event:
            rows = conn.execute("""select distinct on (coalesce(payload->>'event_id', event_id::text))
                                          event_id::text, occurred_at, content, payload, privacy_class
                                   from core.events where source = 'calendar' and event_type = 'calendar.event'
                                     and (payload->>'event_id' = %s or event_id::text = %s)
                                   order by coalesce(payload->>'event_id', event_id::text), ingested_at desc, occurred_at desc""",
                                (calendar_event, calendar_event)).fetchall()
        else:
            since, until = since or now - timedelta(days=30), until or now + timedelta(days=60)
            rows = conn.execute("""select distinct on (coalesce(payload->>'event_id', event_id::text))
                                          event_id::text, occurred_at, content, payload, privacy_class
                                   from core.events where source = 'calendar' and event_type = 'calendar.event'
                                     and coalesce(payload->>'event_id', event_id::text) in (
                                         select coalesce(payload->>'event_id', event_id::text) from core.events
                                         where source = 'calendar' and event_type = 'calendar.event'
                                           and occurred_at >= %s and occurred_at < %s)
                                   order by coalesce(payload->>'event_id', event_id::text), ingested_at desc, occurred_at desc""",
                                (since, until)).fetchall()
        n, changed, retracted = 0, [], 0
        for r in rows:
            p = r["payload"] or {}
            ref = f"cal:{p.get('event_id') or r['event_id']}"
            if any(x in (p.get("calendar_id") or "") for x in NOISE_CALENDARS) or p.get("status") == "cancelled":
                retracted += _retract_ref(conn, "flows.appointments", ref, "cancelled or not a personal calendar")
                continue
            start = _when(p.get("start"), z) or r["occurred_at"]
            end = _when(p.get("end"), z) or start
            title = (r["content"] or "").split("\n", 1)[0].strip() or "Rendez-vous"
            loc = (p.get("location") or "").replace("\n", ", ").strip() or None
            whole_day = bool((p.get("start") or {}).get("date"))
            when = f"le {start.astimezone(z):%d/%m}" if whole_day else _span(start, end, z)
            content = f"Rendez-vous prévu « {title} » {when}" + (f" à {loc}" if loc else "")
            attrs = {"start": start, "end": end, "title": title, "location": loc, "whole_day": whole_day,
                     "attendees": [a.get("email") for a in p.get("attendees") or [] if a.get("email")][:20],
                     "calendar_event": p.get("event_id"), "tz": (p.get("start") or {}).get("timeZone") or str(z)}
            _upsert(conn, kind="appointment", builder="flows.appointments", ref=ref, content=content, attributes=attrs,
                    event_ids=[r["event_id"]], privacy_class=r["privacy_class"], at=start.astimezone(timezone.utc),
                    changed=changed)
            n += 1
    return {"appointments": n, "changed": len(changed), "retracted": retracted}


# ───────────────────────────── work sessions (agents) ─────────────────────────────
def work_sessions(since: datetime | None = None, until: datetime | None = None,
                  thread: tuple[str, str] | None = None) -> dict:
    """The owner's work with W.Alter: per agent thread and local day, when, how much, on which subject. `thread` =
    event-driven: the local days of [since, until] of that thread only; without it, every thread (reconciliation)."""
    from .extract2 import _noise
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=2), until or now
    z = tz()
    # whole local days: a day's session is always rebuilt from all of that day's messages (a window cut mid-day would
    # restate it with fewer messages, then the next event would restate it again)
    since = datetime.combine(since.astimezone(z).date(), datetime.min.time(), z)
    until = datetime.combine(until.astimezone(z).date() + timedelta(days=1), datetime.min.time(), z)
    changed: list = []
    with connection() as conn:
        rows = conn.execute("""select event_id::text, source, thread_id, event_type, occurred_at, privacy_class, content,
                                      payload->>'model' model, payload->>'cwd' cwd
                               from core.events where source = any(%s) and event_type in ('message.sent','message.received')
                                 and thread_id is not null and occurred_at >= %s and occurred_at < %s
                                 and (%s::text is null or (source = %s and thread_id = %s))
                               order by occurred_at""",
                            (list(RUNTIMES), since, until, thread[0] if thread else None,
                             thread[0] if thread else None, thread[1] if thread else None)).fetchall()
        groups = defaultdict(list)
        for r in rows:
            if r["event_type"] == "message.sent" and _noise(r):
                continue
            groups[(r["source"], r["thread_id"], r["occurred_at"].astimezone(z).date())].append(r)
        n = 0
        for (src, th, day), msgs in groups.items():
            owner = [m for m in msgs if m["event_type"] == "message.sent"]
            if not owner:
                continue
            subj = conn.execute("""select v.view_key, coalesce(g.title, v.title) title from views.member m
                                   join views.view v on v.view_key = m.view_key
                                   left join views.view g on g.view_key = 'g1:' || v.view_key
                                   where m.session_id like %s group by 1, 2 order by count(*) desc limit 1""",
                                (f"{src}/%/{th}",)).fetchone()
            cls = privacy.strictest(*(m["privacy_class"] for m in msgs))
            first, last = msgs[0]["occurred_at"], msgs[-1]["occurred_at"]
            content = (f"Travail avec W.Alter ({src}) {_span(first, last, z)} : {len(owner)} messages de Monsieur"
                       + (f", sujet « {subj['title']} »" if subj and subj["title"] else ""))
            attrs = {"start": first, "end": last, "source": src, "thread": th, "day": str(day),
                     "owner_messages": len(owner), "messages": len(msgs), "subject": subj["view_key"] if subj else None,
                     "tz": str(z)}
            _upsert(conn, kind="work_session", builder="flows.work_sessions", ref=f"work:{src}:{th}:{day}",
                    content=content, attributes=attrs, event_ids=[m["event_id"] for m in owner][:200],
                    privacy_class=cls, at=first, changed=changed)
            n += 1
    return {"work_sessions": n, "changed": len(changed)}


def tick(since: datetime | None = None, until: datetime | None = None) -> dict:
    """Reconciliation: recompute every flow over its window. Writes (and publishes) only what differs — after an
    event-driven day, a difference means an event was missed."""
    out = {}
    for name, fn in (("visits", visits), ("conversations", conversations), ("appointments", appointments),
                     ("work_sessions", work_sessions)):
        try:
            out[name] = fn(since, until) if name != "appointments" else fn()
        except Exception as e:  # one flow failing never stops the others
            log.exception("flow %s failed", name)
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out
