"""Deterministic flows (Memory V1 P1.4): the raw streams turned into dated observations, without any model call.

  visits         GPS samples (Overland, local_only) → stays: points within RADIUS_M of the running centre (or on the
                 same Wi-Fi network) for at least MIN_STAY; each stay belongs to a place entity (local_only: its
                 coordinates and its name — the Wi-Fi network — never leave the VM); the place where the nights are
                 spent is marked as the probable home. Nothing is geocoded, nothing is interpreted by a cloud service.
  conversations  messages of a chat (Beeper, Gmail) grouped into bursts (a gap over BURST_GAP opens a new one):
                 who, how many, when — the class of the burst is the strictest of its messages
  appointments   personal calendar events (holiday and week-number calendars excluded): planned, not attended
  work_sessions  the owner's conversations with W.Alter's agents, per thread and local day, with their subject
All are V1 knowledge (core.derived_items, generation g1, epistemic observed, derived_by flows.*), upserted by a
stable ref: rebuilding a window gives the same rows; a stay that no longer exists after a rebuild is retracted.
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
NOISE_CALENDARS = ("#holiday@", "#weeknum@", "#contacts@")


def tz() -> ZoneInfo:
    return ZoneInfo(organic.settings().get("periods", {}).get("tz", "Asia/Bangkok"))


def _m(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _upsert(conn, *, kind: str, builder: str, ref: str, content: str, attributes: dict, event_ids: list[str],
            privacy_class: str, at: datetime, entities: list[str] | None = None) -> str:
    row = conn.execute("""select item_id::text, privacy_class from core.derived_items where derived_by = %s
                          and source_refs->>'ref' = %s""", (builder, ref)).fetchone()
    cls = privacy.strictest(privacy_class, row["privacy_class"]) if row else privacy_class
    if row:
        conn.execute("""update core.derived_items set content = %s, attributes = %s, source_event_ids = %s::uuid[],
                          privacy_class = %s, valid_from = %s, status = 'derived', subject_entity_ids = %s::uuid[]
                        where item_id = %s""", (content, json.dumps(attributes, ensure_ascii=False, default=str),
                                                event_ids, cls, at, entities or [], row["item_id"]))
        return row["item_id"]
    return conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                               source_event_ids, source_refs, valid_from, confidence, privacy_class, generation, epistemic,
                               stage, scope, subject_entity_ids)
                           values (%s, %s, %s, 'derived', %s, '1', %s::uuid[], %s, %s, 1.0, %s, 'g1', 'observed', 'stated',
                                   'durable', %s::uuid[]) returning item_id::text""",
                        (kind, content, json.dumps(attributes, ensure_ascii=False, default=str), builder, event_ids,
                         json.dumps({"ref": ref}), at, cls, entities or [])).fetchone()["item_id"]


def _retract_missing(conn, builder: str, since: datetime, until: datetime, keep: set[str]) -> int:
    rows = conn.execute("""update core.derived_items set status = 'retracted',
                               attributes = attributes || '{"retracted_reason": "not found again on rebuild"}'
                           where derived_by = %s and generation = 'g1' and status = 'derived'
                             and valid_from >= %s and valid_from < %s and not (item_id = any(%s::uuid[]))
                           returning item_id::text""", (builder, since, until, list(keep))).fetchall()
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
            conn.execute("update core.entities set attributes = attributes || %s, updated_at = now() where entity_id = %s",
                         (json.dumps({"wifis": wifis}), r["entity_id"]))
            return r["entity_id"]
    name = stay["wifi"] or f"Lieu {stay['centre'][0]:.4f}, {stay['centre'][1]:.4f}"
    return entities.ensure(conn, "place", name, attributes={"lat": round(stay["centre"][0], 6),
                                                            "lng": round(stay["centre"][1], 6), "radius_m": PLACE_RADIUS_M,
                                                            "wifis": [stay["wifi"]] if stay["wifi"] else [],
                                                            "origin": "flows.visits", "confirmed": False},
                           privacy_class="local_only")


def visits(since: datetime | None = None, until: datetime | None = None) -> dict:
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=2), until or now
    z = tz()
    with connection() as conn:
        rows = conn.execute("""select event_id::text, occurred_at, (payload->>'lat')::float lat, (payload->>'lng')::float lng,
                                      (payload->>'accuracy_m')::float accuracy,
                                      payload->'raw'->'properties'->>'wifi' wifi
                               from core.events e where source = 'overland' and event_type = 'location.sample'
                                 and occurred_at >= %s and occurred_at < %s and payload ? 'lat'
                                 and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                                                 and r.source = 'overland'
                                                 and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
                               order by occurred_at""", (since - MAX_GAP, until)).fetchall()
    samples = [{"id": r["event_id"], "at": r["occurred_at"], "lat": r["lat"], "lng": r["lng"],
                "accuracy": r["accuracy"], "wifi": (r["wifi"] or "").strip() or None} for r in rows]
    found, keep = stays(samples), set()
    from . import entities
    with connection() as conn:
        me = entities.owner_id(conn)
        for s in found:
            if s["end"] < since:
                continue
            place = _place(conn, s)
            pname = conn.execute("select canonical_name from core.entities where entity_id = %s", (place,)).fetchone()["canonical_name"]
            ids = [p["id"] for p in s["pts"]]
            sample_ids = ids if len(ids) <= 60 else [ids[int(k * (len(ids) - 1) / 59)] for k in range(60)]
            attrs = {"start": s["start"], "end": s["end"], "lat": round(s["centre"][0], 6), "lng": round(s["centre"][1], 6),
                     "radius_m": s["radius_m"], "points": len(ids), "wifi": s["wifi"], "place_id": place, "tz": str(z)}
            iid = _upsert(conn, kind="visit", builder="flows.visits", ref=f"visit:{s['start'].isoformat()}",
                          content=f"Présence à « {pname} » {_span(s['start'], s['end'], z)} ({_dur(s['end'] - s['start'])})",
                          attributes=attrs, event_ids=sample_ids, privacy_class="local_only", at=s["start"], entities=[place])
            keep.add(iid)
            if me:
                entities.relate(conn, me, "visited", place, sample_ids[:5], "local_only", s["start"], derived_by="flows.visits")
        retracted = _retract_missing(conn, "flows.visits", since, until - MIN_STAY, keep)
        homes = mark_home(conn)
    return {"samples": len(samples), "visits": len(keep), "retracted": retracted, "home": homes}


def mark_home(conn) -> int:
    """The place with the most local night hours (00:00-06:00) over its visits is the probable home."""
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
    conn.execute("""update core.entities set attributes = attributes - 'home' where entity_type = 'place'
                    and attributes ? 'home' and entity_id <> %s""", (home,))
    conn.execute("""update core.entities set attributes = attributes || '{"home": true}' where entity_id = %s""", (home,))
    return 1


# ───────────────────────────── conversations (Beeper, Gmail) ─────────────────────────────
def conversations(since: datetime | None = None, until: datetime | None = None, sources=("beeper", "gmail")) -> dict:
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=2), until or now
    z = tz()
    with connection() as conn:
        rows = conn.execute("""
            select e.event_id::text, e.source, e.event_type, e.thread_id, e.occurred_at, e.privacy_class,
                   e.actor_identity_id::text actor, coalesce(e.payload->'chat'->>'title', e.payload->>'subject') title,
                   coalesce(e.payload->'chat'->>'network', e.source) network, e.payload->'chat'->>'type' chat_type,
                   l.entity_id::text entity, coalesce(en.canonical_name, i.display_name) who
            from core.events e
            left join core.identity_links l on l.identity_id = e.actor_identity_id
            left join core.entities en on en.entity_id = l.entity_id
            left join core.source_identities i on i.identity_id = e.actor_identity_id
            where e.source = any(%s) and e.event_type in ('message.sent','message.received','email.sent','email.received')
              and e.thread_id is not null and e.occurred_at >= %s and e.occurred_at < %s
            order by e.thread_id, e.occurred_at""", (list(sources), since - BURST_GAP, until)).fetchall()
    by_thread = defaultdict(list)
    for r in rows:
        by_thread[(r["source"], r["thread_id"])].append(r)
    keep, n = set(), 0
    from . import entities
    with connection() as conn:
        me = entities.owner_id(conn)
        for (src, thread), msgs in by_thread.items():
            bursts, cur = [], [msgs[0]]
            for m in msgs[1:]:
                if m["occurred_at"] - cur[-1]["occurred_at"] > BURST_GAP:
                    bursts.append(cur); cur = []
                cur.append(m)
            bursts.append(cur)
            for b in bursts:
                if b[-1]["occurred_at"] < since:
                    continue
                owner = sum(1 for m in b if m["event_type"] in ("message.sent", "email.sent"))
                people = {m["entity"]: m["who"] for m in b if m["entity"] and m["entity"] != me and m["entity"]}
                names = [w for w in dict.fromkeys(m["who"] for m in b if m["entity"] != me and m["who"])][:5]
                cls = privacy.strictest(*(m["privacy_class"] for m in b))
                title = b[0]["title"] or ", ".join(names) or thread[:12]
                kind_word = "Échange" if src != "gmail" else "Échange de courriels"
                content = (f"{kind_word} {b[0]['network']} « {title} »{' (groupe)' if b[0]['chat_type'] == 'group' else ''} "
                           f"{_span(b[0]['occurred_at'], b[-1]['occurred_at'], z)} : {len(b)} messages dont {owner} de "
                           f"Monsieur" + (f" ; avec {', '.join(names)}" if names else ""))
                attrs = {"start": b[0]["occurred_at"], "end": b[-1]["occurred_at"], "thread": thread, "source": src,
                         "network": b[0]["network"], "title": b[0]["title"], "chat_type": b[0]["chat_type"],
                         "messages": len(b), "owner_messages": owner, "participants": list(people), "tz": str(z)}
                iid = _upsert(conn, kind="conversation", builder="flows.conversations",
                              ref=f"conv:{src}:{thread}:{b[0]['occurred_at'].isoformat()}", content=content,
                              attributes=attrs, event_ids=[m["event_id"] for m in b][:300], privacy_class=cls,
                              at=b[0]["occurred_at"], entities=list(people)[:20])
                keep.add(iid); n += 1
                if me and owner:
                    for eid in list(people)[:20]:
                        entities.relate(conn, me, "exchanged_with", eid, [b[0]["event_id"]], cls, b[0]["occurred_at"],
                                        derived_by="flows.conversations")
    return {"threads": len(by_thread), "bursts": n}


# ───────────────────────────── appointments (calendar) ─────────────────────────────
def _when(v: dict | None, default_tz: ZoneInfo) -> datetime | None:
    if not v:
        return None
    if v.get("dateTime"):
        return datetime.fromisoformat(v["dateTime"])
    if v.get("date"):
        return datetime.fromisoformat(v["date"]).replace(tzinfo=default_tz)
    return None


def appointments(since: datetime | None = None, until: datetime | None = None) -> dict:
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=30), until or now + timedelta(days=60)
    z = tz()
    with connection() as conn:
        rows = conn.execute("""select event_id::text, occurred_at, content, payload, privacy_class from core.events
                               where source = 'calendar' and event_type = 'calendar.event'
                                 and occurred_at >= %s and occurred_at < %s""", (since, until)).fetchall()
        n = 0
        for r in rows:
            p = r["payload"] or {}
            if any(x in (p.get("calendar_id") or "") for x in NOISE_CALENDARS) or p.get("status") == "cancelled":
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
            _upsert(conn, kind="appointment", builder="flows.appointments", ref=f"cal:{p.get('event_id') or r['event_id']}",
                    content=content, attributes=attrs, event_ids=[r["event_id"]], privacy_class=r["privacy_class"],
                    at=start.astimezone(timezone.utc))
            n += 1
    return {"appointments": n}


# ───────────────────────────── work sessions (agents) ─────────────────────────────
def work_sessions(since: datetime | None = None, until: datetime | None = None) -> dict:
    """The owner's work with W.Alter: per agent thread and local day, when, how much, on which subject."""
    from .extract2 import _noise
    now = datetime.now(timezone.utc)
    since, until = since or now - timedelta(days=2), until or now
    z = tz()
    with connection() as conn:
        rows = conn.execute("""select event_id::text, source, thread_id, event_type, occurred_at, privacy_class, content,
                                      payload->>'model' model, payload->>'cwd' cwd
                               from core.events where source = any(%s) and event_type in ('message.sent','message.received')
                                 and thread_id is not null and occurred_at >= %s and occurred_at < %s
                               order by occurred_at""", (list(RUNTIMES), since, until)).fetchall()
        groups = defaultdict(list)
        for r in rows:
            if r["event_type"] == "message.sent" and _noise(r):
                continue
            groups[(r["source"], r["thread_id"], r["occurred_at"].astimezone(z).date())].append(r)
        n = 0
        for (src, thread, day), msgs in groups.items():
            owner = [m for m in msgs if m["event_type"] == "message.sent"]
            if not owner:
                continue
            subj = conn.execute("""select v.view_key, coalesce(g.title, v.title) title from views.member m
                                   join views.view v on v.view_key = m.view_key
                                   left join views.view g on g.view_key = 'g1:' || v.view_key
                                   where m.session_id like %s group by 1, 2 order by count(*) desc limit 1""",
                                (f"{src}/%/{thread}",)).fetchone()
            cls = privacy.strictest(*(m["privacy_class"] for m in msgs))
            first, last = msgs[0]["occurred_at"], msgs[-1]["occurred_at"]
            content = (f"Travail avec W.Alter ({src}) {_span(first, last, z)} : {len(owner)} messages de Monsieur"
                       + (f", sujet « {subj['title']} »" if subj and subj["title"] else ""))
            attrs = {"start": first, "end": last, "source": src, "thread": thread, "day": str(day),
                     "owner_messages": len(owner), "messages": len(msgs), "subject": subj["view_key"] if subj else None,
                     "tz": str(z)}
            _upsert(conn, kind="work_session", builder="flows.work_sessions", ref=f"work:{src}:{thread}:{day}",
                    content=content, attributes=attrs, event_ids=[m["event_id"] for m in owner][:200],
                    privacy_class=cls, at=first)
            n += 1
    return {"work_sessions": n}


def tick(since: datetime | None = None, until: datetime | None = None) -> dict:
    out = {}
    for name, fn in (("visits", visits), ("conversations", conversations), ("appointments", appointments),
                     ("work_sessions", work_sessions)):
        try:
            out[name] = fn(since, until) if name != "appointments" else fn()
        except Exception as e:  # one flow failing never stops the others
            log.exception("flow %s failed", name)
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out
