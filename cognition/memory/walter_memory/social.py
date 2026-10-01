"""P4 — identities → entities (deterministic), group membership graph, Kardex V1 relationship baselines and
communication deviations (L0, no LLM), and the fast person card (§24).

Merge only on strong signals (same phone / e-mail, Kardex contact ↔ its Beeper chat, Monsieur's own accounts,
W.Alter's own accounts). Name-only matches are proposed (core.identity_links status 'proposed'), never merged.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .db import connection

VERSION = "social-1"
WA_PHONE = re.compile(r"^@whatsapp_(\d{8,15}):")
RAW_ID_NAME = re.compile(r"^@[\w.-]+:[\w.-]+$")


def _norm_phone(p: str) -> str | None:
    d = re.sub(r"\D", "", p or "")
    return f"+{d}" if 8 <= len(d) <= 15 else None


def _good_name(n: str | None) -> str | None:
    if not n or RAW_ID_NAME.match(n) or n.startswith("+") and n[1:].isdigit():
        return None
    return n.strip()


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def resolve_identities() -> dict:
    with connection() as conn:
        ids = conn.execute("""select identity_id::text, source, account, external_id, display_name, phones, emails, is_self
                              from core.source_identities""").fetchall()
        uf, by_key = UF(), defaultdict(list)
        method: dict[str, str] = {}
        for i in ids:
            uf.find(i["identity_id"])
            keys = {f"phone:{p}" for p in map(_norm_phone, i["phones"] or []) if p}
            m = WA_PHONE.match(i["external_id"] or "")
            if m:
                keys.add(f"phone:+{m.group(1)}")
            keys |= {f"email:{e.lower()}" for e in i["emails"] or []}
            if i["is_self"]:
                keys.add("self:monsieur")
            if i["external_id"] == "walter" or (i["account"] == "telegram" and (i["display_name"] or "").lower() == "w.alter"):
                keys.add("self:walter")
            for k in keys:
                by_key[k].append(i["identity_id"])
        for k, members in by_key.items():
            for other in members[1:]:
                uf.union(members[0], other)
                method[other] = method[members[0]] = k.split(":")[0]
        # Kardex contact ↔ the counterpart of its mapped Beeper chat (kardex.channels.platform_id = chat id)
        pairs = conn.execute("""
            select distinct ki.identity_id::text a, e.actor_identity_id::text b
            from kardex.channels ch
            join core.source_identities ki on ki.source = 'kardex_legacy' and ki.external_id = 'kardex_contact:' || ch.contact_id
            join core.events e on e.source = 'beeper' and e.thread_id = ch.platform_id
                               and e.event_type = 'message.received' and (e.payload->'chat'->>'type') = 'single'
            where ch.platform_id is not null""").fetchall()
        for p in pairs:
            uf.union(p["a"], p["b"]); method[p["a"]] = method[p["b"]] = "kardex_channel"
        clusters = defaultdict(list)
        for i in ids:
            clusters[uf.find(i["identity_id"])].append(i)
        created = linked = 0
        existing = {r["identity_id"]: r["entity_id"] for r in conn.execute(
            "select identity_id::text, entity_id::text from core.identity_links where status = 'confirmed'").fetchall()}
        for members in clusters.values():
            ent = next((existing[m["identity_id"]] for m in members if m["identity_id"] in existing), None)
            names = Counter(n for n in (_good_name(m["display_name"]) for m in members) if n)
            is_self = any(m["is_self"] for m in members)
            is_walter = any(m["external_id"] == "walter" for m in members)
            phones = [p for m in members for p in ([f"+{WA_PHONE.match(m['external_id']).group(1)}"]
                                                   if WA_PHONE.match(m["external_id"] or "") else []) + list(m["phones"] or [])]
            name = ("Monsieur" if is_self else "W.Alter" if is_walter else
                    names.most_common(1)[0][0] if names else phones[0] if phones else members[0]["external_id"])
            etype = "agent" if is_walter else "person"
            if ent is None:
                ent = conn.execute("""insert into core.entities (entity_type, canonical_name, aliases, attributes)
                                      values (%s, %s, %s, %s) returning entity_id::text""",
                                   (etype, name, sorted(set(names) - {name}),
                                    '{"is_self": true}' if is_self else '{}')).fetchone()["entity_id"]
                created += 1
            else:
                conn.execute("""update core.entities set
                                    aliases = coalesce((select array_agg(distinct a) from unnest(aliases || %s::text[]) a), '{}'),
                                    canonical_name = case when canonical_name ~ '^@' then %s else canonical_name end,
                                    updated_at = now() where entity_id = %s""", (sorted(set(names)), name, ent))
            for m in members:
                if m["identity_id"] not in existing:
                    how = method.get(m["identity_id"], "single_identity")
                    conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method, provenance)
                                    values (%s, %s, 'confirmed', %s, %s, %s) on conflict do nothing""",
                                 (m["identity_id"], ent, 1.0 if how != "single_identity" else 0.9, how,
                                  '{"processor": "%s"}' % VERSION))
                    linked += 1
        # Kardex contacts ↔ entities
        conn.execute("""update core.entities en set kardex_contact_id = substr(si.external_id, 16)::int
                        from core.source_identities si join core.identity_links l on l.identity_id = si.identity_id
                        where si.source = 'kardex_legacy' and si.external_id like 'kardex_contact:%%'
                          and l.entity_id = en.entity_id and en.kardex_contact_id is null""")
        conn.execute("""update core.entities set kardex_contact_id = 0 where (attributes->>'is_self')::boolean and kardex_contact_id is null""")
        # name-only matches across different entities → proposals for Monsieur, never merges
        proposals = conn.execute("""
            insert into core.identity_links (identity_id, entity_id, status, confidence, method, provenance)
            select l2.identity_id, e1.entity_id, 'proposed', 0.4, 'name_match', '{"rule": "same display name, other network"}'
            from core.entities e1 join core.entities e2 on lower(e1.canonical_name) = lower(e2.canonical_name)
                 and e1.entity_id < e2.entity_id and e1.entity_type = 'person' and e2.entity_type = 'person'
                 and length(e1.canonical_name) >= 4 and e1.canonical_name !~ '^@'
            join core.identity_links l2 on l2.entity_id = e2.entity_id and l2.status = 'confirmed'
            on conflict do nothing""").rowcount
    return {"identities": len(ids), "clusters": len(clusters), "entities_created": created, "links": linked,
            "name_proposals": proposals}


def sync_groups() -> dict:
    """Group chats → group entities; members → member_of relationships (valid_from = first message)."""
    with connection() as conn:
        groups = conn.execute("""
            select e.thread_id, max(e.payload->'chat'->>'title') title, max(e.source_account) network,
                   min(e.occurred_at) first, max(e.occurred_at) last
            from core.events e where e.source = 'beeper' and e.payload->'chat'->>'type' = 'group'
            group by e.thread_id""").fetchall()
        n_rel = 0
        for g in groups:
            ent = conn.execute("""select entity_id from core.entities where entity_type = 'group' and attributes->>'thread_id' = %s""",
                               (g["thread_id"],)).fetchone()
            if not ent:
                ent = conn.execute("""insert into core.entities (entity_type, canonical_name, attributes)
                                      values ('group', %s, jsonb_build_object('thread_id', %s::text, 'network', %s::text))
                                      returning entity_id""", (g["title"] or g["thread_id"], g["thread_id"], g["network"])).fetchone()
            n_rel += conn.execute("""
                insert into core.relationships (subject_id, predicate, object_id, valid_from, confidence, status, derived_by,
                                                processor_version)
                select l.entity_id, 'member_of', %s, min(e.occurred_at), 0.9, 'derived', 'social.sync_groups', %s
                from core.events e join core.identity_links l on l.identity_id = e.actor_identity_id and l.status = 'confirmed'
                where e.source = 'beeper' and e.thread_id = %s
                  and not exists (select 1 from core.relationships r where r.subject_id = l.entity_id
                                  and r.predicate = 'member_of' and r.object_id = %s)
                group by l.entity_id""", (ent["entity_id"], VERSION, g["thread_id"], ent["entity_id"])).rowcount
    return {"groups": len(groups), "memberships_added": n_rel}


BASELINE_SQL = """
with self_ent as (select entity_id from core.entities where (attributes->>'is_self')::boolean limit 1),
single as (   -- single chats and their counterpart entity
  select e.thread_id, min(l.entity_id::text)::uuid as other
  from core.events e join core.identity_links l on l.identity_id = e.actor_identity_id and l.status = 'confirmed'
       join core.entities pe on pe.entity_id = l.entity_id and pe.entity_type = 'person'
  where e.source = 'beeper' and e.payload->'chat'->>'type' = 'single' and e.event_type = 'message.received'
    and l.entity_id not in (select entity_id from self_ent)
  group by e.thread_id having count(distinct l.entity_id) = 1),
msgs as (
  select s.other, e.source_account, e.occurred_at, e.event_type = 'message.sent' as me, length(coalesce(e.content,'')) len,
         lag(e.occurred_at) over w as prev_at, lag(e.event_type = 'message.sent') over w as prev_me
  from core.events e join single s on s.thread_id = e.thread_id
  where e.source = 'beeper' and e.event_type in ('message.sent','message.received')
    and e.occurred_at >= now() - %(win)s::interval
  window w as (partition by e.thread_id order by e.occurred_at))
select other as entity_id, array_agg(distinct source_account) channels, count(*) messages,
       count(*) filter (where me) from_me, count(*) filter (where not me) from_them,
       count(*)::real / greatest(1, extract(epoch from (least(now(), max(occurred_at)) - greatest(min(occurred_at), now() - %(win)s::interval))) / 86400) msgs_per_day,
       count(distinct occurred_at::date) active_days,
       (count(*) filter (where me and (prev_at is null or occurred_at - prev_at > interval '6 hours')))::real
         / nullif(count(*) filter (where prev_at is null or occurred_at - prev_at > interval '6 hours'), 0) initiation_ratio_me,
       percentile_cont(0.5) within group (order by extract(epoch from occurred_at - prev_at))
         filter (where me and prev_me = false and occurred_at - prev_at < interval '24 hours') median_reply_me_s,
       percentile_cont(0.5) within group (order by extract(epoch from occurred_at - prev_at))
         filter (where not me and prev_me and occurred_at - prev_at < interval '24 hours') median_reply_them_s,
       avg(len) filter (where me) avg_len_me, avg(len) filter (where not me) avg_len_them,
       min(occurred_at) first_contact, max(occurred_at) last_contact
from msgs group by other"""

WINDOWS = {"7d": "7 days", "14d": "14 days", "30d": "30 days", "90d": "90 days", "365d": "365 days", "all": "100 years"}


def compute_baselines() -> dict:
    out = {}
    with connection() as conn:
        for name, interval in WINDOWS.items():
            rows = conn.execute(BASELINE_SQL, {"win": interval}).fetchall()
            conn.execute("delete from kardex.relationship_baselines where window_name = %s", (name,))
            for r in rows:
                conn.execute("""insert into kardex.relationship_baselines (entity_id, window_name, channels, messages, from_me,
                                    from_them, msgs_per_day, active_days, initiation_ratio_me, median_reply_me_s,
                                    median_reply_them_s, avg_len_me, avg_len_them, first_contact, last_contact, processor_version)
                                values (%(entity_id)s, %(w)s, %(channels)s, %(messages)s, %(from_me)s, %(from_them)s, %(msgs_per_day)s,
                                        %(active_days)s, %(initiation_ratio_me)s, %(median_reply_me_s)s, %(median_reply_them_s)s,
                                        %(avg_len_me)s, %(avg_len_them)s, %(first_contact)s, %(last_contact)s, %(v)s)""",
                             {**r, "w": name, "v": VERSION})
            out[name] = len(rows)
    return out


def detect_deviations(min_baseline_msgs: int = 30) -> int:
    """Compare the last 14 days with the 90-day baseline; record measurable changes only (no cause)."""
    checks = [  # metric, baseline column, threshold test, wording
        ("msgs_per_day", lambda b, c: c < 0.3 * b or c > 3 * b, "volume de messages par jour"),
        ("median_reply_them_s", lambda b, c: c > 4 * b and c > 600, "délai de réponse de la personne"),
        ("initiation_ratio_me", lambda b, c: abs(c - b) > 0.3, "part des conversations lancées par Monsieur"),
        ("avg_len_them", lambda b, c: c < 0.4 * b, "longueur moyenne de ses messages"),
    ]
    n = 0
    with connection() as conn:
        rows = conn.execute("""select b.entity_id, b.messages bm, c.messages cm, e.canonical_name,
                                      b.msgs_per_day b_msgs_per_day, c.msgs_per_day c_msgs_per_day,
                                      b.median_reply_them_s b_median_reply_them_s, c.median_reply_them_s c_median_reply_them_s,
                                      b.initiation_ratio_me b_initiation_ratio_me, c.initiation_ratio_me c_initiation_ratio_me,
                                      b.avg_len_them b_avg_len_them, c.avg_len_them c_avg_len_them
                               from kardex.relationship_baselines b
                               join core.entities e on e.entity_id = b.entity_id
                               left join kardex.relationship_baselines c on c.entity_id = b.entity_id and c.window_name = '14d'
                               where b.window_name = '90d' and b.messages >= %s""", (min_baseline_msgs,)).fetchall()
        for r in rows:
            for metric, test, label in checks:
                base = r[f"b_{metric}"]
                cur = r[f"c_{metric}"] if r["cm"] else (0.0 if metric == "msgs_per_day" else None)
                if base is None or cur is None or base == 0:
                    continue
                if test(base, cur):
                    n += conn.execute("""insert into kardex.communication_deviations (entity_id, metric, baseline, current, ratio,
                                             baseline_window, current_window, sample_size, observation, processor_version)
                                         values (%s,%s,%s,%s,%s,'90d','14d',%s,%s,%s) on conflict do nothing""",
                                      (r["entity_id"], metric, base, cur, cur / base if base else None, r["bm"],
                                       f"Écart mesuré avec {r['canonical_name']} : {label} {base:.2f} → {cur:.2f} "
                                       f"(14 j vs 90 j). Cause inconnue.", VERSION)).rowcount
    return n


def find_entities(query: str, limit: int = 5) -> list[dict]:
    with connection() as conn:
        return conn.execute("""
            select en.entity_id::text, en.entity_type, en.canonical_name, en.aliases, en.kardex_contact_id,
                   coalesce(b.messages, 0) messages, b.last_contact
            from core.entities en
            left join kardex.relationship_baselines b on b.entity_id = en.entity_id and b.window_name = 'all'
            where en.status = 'active' and (en.canonical_name ilike %(q)s or exists (select 1 from unnest(en.aliases) a where a ilike %(q)s)
               or exists (select 1 from core.identity_links l join core.source_identities si on si.identity_id = l.identity_id
                          where l.entity_id = en.entity_id and l.status = 'confirmed'
                            and (si.display_name ilike %(q)s or si.handles::text ilike %(q)s or %(raw)s = any(si.phones))))
            order by coalesce(b.messages, 0) desc limit %(n)s""", {"q": f"%{query}%", "raw": query, "n": limit}).fetchall()


def person_card(entity_id: str, max_privacy: str = "local_only") -> dict:
    """Fast social card (§24): identity, accounts, relationship metrics, deviations, Kardex knowledge (mention policy
    respected), shared groups, recent interactions, media counts. Deep dive happens through events/objects."""
    from . import privacy
    allowed = privacy.allowed_classes(max_privacy)
    with connection() as conn:
        en = conn.execute("select * from core.entities where entity_id = %s", (entity_id,)).fetchone()
        accounts = conn.execute("""select si.source, si.account, si.display_name, si.handles, si.phones, l.method
                                   from core.identity_links l join core.source_identities si on si.identity_id = l.identity_id
                                   where l.entity_id = %s and l.status = 'confirmed'""", (entity_id,)).fetchall()
        metrics = {r["window_name"]: {k: r[k] for k in ("messages", "from_me", "from_them", "msgs_per_day", "initiation_ratio_me",
                                                         "median_reply_me_s", "median_reply_them_s", "avg_len_me", "avg_len_them",
                                                         "first_contact", "last_contact", "channels")}
                   for r in conn.execute("select * from kardex.relationship_baselines where entity_id = %s", (entity_id,)).fetchall()}
        deviations = conn.execute("""select metric, observation, detected_on from kardex.communication_deviations
                                     where entity_id = %s and acknowledged_at is null order by detected_on desc limit 5""",
                                  (entity_id,)).fetchall()
        kardex = {}
        if en["kardex_contact_id"] is not None:
            c = conn.execute("""select canonical_name, relationship_type, relationship_status, occupation, location_current,
                                       languages, interests from kardex.contacts where id = %s""", (en["kardex_contact_id"],)).fetchone()
            claims = conn.execute("""select claim, mention_policy, knowledge_origin, confidence from kardex.claims
                                     where contact_id = %s and status <> 'superseded' and mention_policy <> 'never_reference'
                                     order by confidence desc limit 15""", (en["kardex_contact_id"],)).fetchall()
            kardex = {"contact": c, "claims": claims}
        groups = conn.execute("""select g.canonical_name, g.attributes->>'network' network from core.relationships r
                                 join core.entities g on g.entity_id = r.object_id
                                 where r.subject_id = %s and r.predicate = 'member_of' limit 15""", (entity_id,)).fetchall()
        recent = conn.execute("""select e.occurred_at, e.event_type, e.source_account, left(e.content, 200) content
                                 from core.events e join core.identity_links l on l.identity_id = e.actor_identity_id
                                 where l.entity_id = %s and l.status = 'confirmed' and e.event_type like 'message.%%'
                                   and e.privacy_class = any(%s)
                                 order by e.occurred_at desc limit 8""", (entity_id, allowed)).fetchall()
        media = conn.execute("""select o.kind, count(*) n from core.objects o join core.object_links ol on ol.object_id = o.id
                                where ol.target_type = 'beeper_message' and split_part(ol.target_id, '|', 1) in (
                                  select distinct e.thread_id from core.events e join core.identity_links l on l.identity_id = e.actor_identity_id
                                  where l.entity_id = %s and e.payload->'chat'->>'type' = 'single')
                                group by 1""", (entity_id,)).fetchall()
    return {"entity": {k: en[k] for k in ("entity_id", "entity_type", "canonical_name", "aliases", "kardex_contact_id")},
            "accounts": accounts, "relationship": metrics, "deviations": deviations, "kardex": kardex,
            "shared_groups": groups, "recent_interactions": recent, "media": {m["kind"]: m["n"] for m in media}}
