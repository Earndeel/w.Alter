"""Projection Relationnel (docs/PROJECTIONS.md § 10, lot P3): « où en est ma relation avec X ? ».

Like the project and personal projections, a READ of what memory already holds — no table, no cache, no model call:
Kardex (the social layer: identities, card, claims, open loops, measured rhythm), the organic knowledge about the
person (core.derived_items whose subject_entity_ids name them: deterministic conversations, plans, statements),
the relations of the person (projects, groups) and the episodes that involve them. For one person (one entity):

  identity       who: name, the networks they are reached on, the Kardex card fields this reader may see
  relation       what is known of the relation with Monsieur, each line by WHO says it:
                   « dit par la personne » (a Kardex claim from their messages, not confirmed),
                   « dit par Monsieur » / « confirmé par Monsieur » (his statement, a confirmed claim, his correction),
                   « vérifié par les données » (measures: first / last exchange, volumes, shared groups),
                   « hypothèse » (an inference: never shown as a fact)
  changes        what changed lately (new or replaced claims and knowledge, new relations), dated
  exchanges      the exchanges as measures (how many, when, on which network, who started) — never their content
  commitments    plans and open loops with them, with their stage (convenu / proposé / tenu ?)
  follow_up      what MAY need a follow-up, deterministic (a passed deadline, a plan with no trace since, a date
                 coming); nothing is created, notified or sent: it is a reading
  contexts       the projects, groups and episodes they belong to: one person, several contexts, never duplicated
  rhythm         the measured rhythm (30 / 90 days) and the measured deviations, as numbers « cause inconnue »:
                 never a psychological or sentimental conclusion
  history        the information replaced or retracted, with its date and what replaced it (append-only memory)

Privacy (P3, 19/11): a cloud reader gets `cloud_allowed` and `redacted_cloud` rows (contacts' phones and e-mails
masked), never `local_only` (counted, not rendered); Kardex claims through read_policy's STRICT cloud rules (not the
owner's « oui tout » reasoning mode: being in a projection is no reason to send a sensitive information to a cloud
model), sensitive claim types and texts flagged by privacy.detect withheld; psychological claims are never read.
A local reader (max_privacy="local_only") gets everything the owner may see.

Homonyms: a name that designates several people returns the candidates (networks, volumes, last exchange), never a
merge and never a guess. Keys: `person:<name>`, `person:<entity id or its first 8 characters>`.
"""
from __future__ import annotations

import contextlib
import re
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import projection as P
from .db import connection

PREFIXES = ("person:", "personne:", "relation:", "contact:")
RECENT = timedelta(days=30)         # « ce qui a récemment changé », the recent exchanges
SOON = timedelta(days=14)           # a date coming (birthday, plan)
QUIET_PLAN = timedelta(days=3)      # a plan whose date passed this long ago with no exchange since: « tenu ? »
CLOUD = ["cloud_allowed", "redacted_cloud"]
LOCAL = ["cloud_allowed", "redacted_cloud", "local_only"]
# claim types a cloud model never gets from a projection, whatever their tagged sensitivity (owner_local sees them)
SENSITIVE_TYPE = re.compile(r"(?i)(sex|dating|medical|health|sant|vice|cannabis|substance|body|physical|religion|"
                            r"politic|ethnic|money|financ|breakup|relationship_(history|preference|status|duration)|"
                            r"boundar|personality|self_|astrolog|zodiac|sleep|caregiving|location|localisation|"
                            r"residence|accommodation|housing|living|contact_info|identity|âge|\bage\b|demograph|family|"
                            r"privacy|info_withheld|osint|nationality|origin)")
WHO_CLAIM = {"person": "dit par la personne", "owner": "dit par Monsieur", "confirmed": "confirmé par Monsieur",
             "public": "source publique", "inferred": "hypothèse, non vérifiée",
             "observed": "observé dans les échanges"}
WHO_ITEM = {"stated_owner": "dit par Monsieur", "stated_third_party": "dit par la personne", "observed": "vérifié par "
            "les données", "agent_reported": "rapporté par W.Alter", "inferred": "hypothèse, non vérifiée"}
METRICS = {"msgs_per_day": ("messages par jour", "{:.1f}"), "median_reply_them_s": ("délai médian de sa réponse", "s"),
           "initiation_ratio_me": ("part des échanges lancés par Monsieur", "%"),
           "avg_len_them": ("longueur moyenne de ses messages", "{:.0f} car.")}
# a claim of these types says who the person is (shown under « Qui »); the others say something of the relation
IDENTITY_TYPE = re.compile(r"(?i)(work|profes|métier|career|education|interest|hobb|language|biograph|background|"
                           r"business|skill|knowledge|music|food|gaming|activity)")
PERSON_LINES = 6                    # at most this many of the person's own unconfirmed statements per section
REL_HINT = re.compile(r"(?i)(\bma relation\b|\bnotre relation\b|\brelation avec\b|o[uù] (j'en suis|en suis-je|on en est|"
                      r"en est-on) avec|\bqui est\b|quoi de neuf (avec|de|du c[ôo]t[ée] de)|\bavec qui\b|"
                      r"\bje (dois|lui dois)\b.*\b(à|a)\b|engagements? (avec|envers|pris)|\bnouvelles? de\b|"
                      r"\bsuivi (avec|de)\b|\bcontact avec\b)")


def kind_of(key: str) -> bool:
    return (key or "").strip().lower().startswith(PREFIXES)


def _target(key: str) -> str:
    k = (key or "").strip()
    for p in PREFIXES:
        if k.lower().startswith(p):
            return k[len(p):].strip()
    return k


def _allowed(max_privacy: str) -> list[str]:
    return LOCAL if max_privacy == "local_only" else CLOUD


@lru_cache(maxsize=20000)
def _sensitive(text: str) -> bool:
    from . import privacy
    return bool(privacy.detect(text or ""))


@lru_cache(maxsize=20000)
def _redact(text: str | None, cloud: bool) -> str:
    if not text or not cloud:
        return text or ""
    from . import privacy
    return privacy.redact(privacy.mask_secrets(text) or "")[0]


# ───────────────────────────── who ─────────────────────────────
def candidates(conn, name: str, limit: int = 8) -> list[dict]:
    """The people this name (or id) designates, the most exchanged with first. Never merged: each is one entity."""
    t = name.strip()
    if re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f-]{4,})?", t.lower()):
        where, args = "e.entity_id::text like %s", [t.lower() + "%"]
    else:
        where = """(lower(unaccent(e.canonical_name)) = lower(unaccent(%s)) or exists (select 1 from unnest(e.aliases) a
                    where lower(unaccent(a)) = lower(unaccent(%s))))"""
        args = [t, t]
    sql = f"""select e.entity_id::text, e.canonical_name, e.kardex_contact_id, coalesce(b.messages, 0) messages,
                     b.last_contact, b.channels,
                     (select array_agg(distinct si.source || '|' || coalesce(si.account, ''))
                      from core.identity_links l join core.source_identities si on si.identity_id = l.identity_id
                      where l.entity_id = e.entity_id and l.status = 'confirmed') networks
              from core.entities e left join kardex.relationship_baselines b
                on b.entity_id = e.entity_id and b.window_name = 'all'
              where e.entity_type = 'person' and e.status = 'active' and {where}
              order by coalesce(b.messages, 0) desc, e.created_at limit %s"""
    rows = conn.execute(sql, (*args, limit)).fetchall()
    if not rows and not where.startswith("e.entity_id"):         # a first name alone: whole word in the name
        rows = conn.execute(sql.replace(where, """(lower(unaccent(e.canonical_name)) ~ ('(^|\\s)' ||
                  regexp_replace(lower(unaccent(%s)), '([.^$*+?()\\[\\]{}|\\\\])', '\\\\\\1', 'g') || '(\\s|$)'))"""),
                            (t, limit)).fetchall()
    return [dict(r, networks=_networks(r["networks"])) for r in rows]


_NET = {"instagramgo": "instagram", "facebookgo": "facebook", "gmail": "e-mail", "google_calendar": "agenda"}


def _networks(raw) -> list[str]:
    """The network names a person is reached on — never the owner's account identifiers (an account id or address
    is not something a reader needs) and never the legacy importers."""
    out = set()
    for x in raw or []:
        source, _, account = x.partition("|")
        if source.startswith("kardex") or source in ("walter", "pytest"):
            continue
        net = account.split(".")[0] if source == "beeper" and account else source
        out.add(_NET.get(net, net))
    return sorted(out)


def resolve(conn, key: str) -> dict:
    """→ {"entity": row} for one person, {"ambiguous": [rows]} for homonyms, {"missing": name} when unknown."""
    name = _target(key)
    c = candidates(conn, name)
    if not c:
        return {"missing": name}
    if len(c) == 1:
        return {"entity": c[0]}
    return {"ambiguous": c, "name": name}


# ───────────────────────────── the projection ─────────────────────────────
def _claims(conn, contact_id: int | None, audience: str, at: datetime | None, cloud: bool) -> dict:
    from . import read_policy
    if contact_id is None:
        return {"current": [], "history": [], "withheld": 0, "pending": 0}
    rows = conn.execute("""with ev as (
                               select ce.claim_id, min(array_position(array['highly_sensitive','sensitive','personal',
                                        'normal'], e.sensitivity)) sens_rank,
                                      bool_or(e.speaker ilike any(array['%%lucas%%','me','owner','monsieur','moi'])) by_owner,
                                      max(e.timestamp) said_at
                               from kardex.claim_evidence ce join kardex.evidence e on e.id = ce.evidence_id
                               where ce.claim_id in (select id from kardex.claims where contact_id = %s) group by 1)
                           select c.id, c.claim, c.claim_type, c.status, c.valid_from, c.valid_to, c.created_at,
                                  c.updated_at, c.mention_policy, c.knowledge_origin, c.disclosure_state, c.sensitivity,
                                  c.confidence, c.supersedes_claim_id, ev.by_owner, ev.said_at,
                                  (array['highly_sensitive','sensitive','personal','normal'])[ev.sens_rank] evidence_sensitivity
                           from kardex.claims c left join ev on ev.claim_id = c.id
                           where c.contact_id = %s and (%s::timestamptz is null or c.created_at <= %s)
                           order by c.created_at""", (contact_id, contact_id, at, at)).fetchall()
    now = at or datetime.now(timezone.utc)
    replaced_by = {r["supersedes_claim_id"]: r for r in rows if r["supersedes_claim_id"]}
    cur, hist, withheld, pending = [], [], 0, 0
    for r in rows:
        # at a date: a claim replaced or retracted later was current then
        status = r["status"] if at is None or (r["updated_at"] or r["created_at"]) <= at else "active"
        then = {**r, "status": status}
        visible, why = read_policy.kardex_claim_visible(then if status in read_policy.CURRENT_CLAIM
                                                        else {**then, "status": "active"}, audience, now,
                                                        strict=True)
        if visible and cloud and (SENSITIVE_TYPE.search(r["claim_type"] or "") or _sensitive(r["claim"])):
            visible = False
        if not visible:
            withheld += 1
            continue
        who = ("confirmed" if status in ("active", "confirmed") and r["knowledge_origin"] != "public_osint" else
               "public" if r["knowledge_origin"] == "public_osint" else
               "inferred" if r["knowledge_origin"] == "inference" or r["disclosure_state"] == "inferred_only" else
               "observed" if r["knowledge_origin"] in ("observed_behavior", "system_observation") else
               "owner" if r["by_owner"] or r["knowledge_origin"] == "user_supplied" else "person")
        line = {"id": f"k{r['id']}", "text": _redact(r["claim"], cloud), "type": r["claim_type"], "who": WHO_CLAIM[who],
                "said": r["said_at"] or r["valid_from"] or r["created_at"], "recorded": r["created_at"],
                "status": status, "sensitive": r["sensitivity"] in ("sensitive", "highly_sensitive")
                or r["mention_policy"] in ("never_reference", "indirect_only")}
        if status in read_policy.CURRENT_CLAIM and not (r["valid_to"] and r["valid_to"] <= now):
            cur.append(line)
            pending += who == "person"
        else:
            nxt = replaced_by.get(r["id"])
            hist.append({**line, "until": (nxt or r)["created_at"] if nxt else r["valid_to"] or r["updated_at"],
                         "replaced_by": f"k{nxt['id']}" if nxt else None,
                         "how": "remplacé" if nxt or status == "superseded" else
                                "expiré" if r["valid_to"] and r["valid_to"] <= now else "retiré"})
    return {"current": cur, "history": hist, "withheld": withheld, "pending": pending}


def _items(conn, eid: str, at: datetime | None, allowed: list[str], cloud: bool) -> dict:
    rows = conn.execute("""select d.item_id::text id, d.kind, d.content, d.status, d.epistemic, d.stage, d.derived_by,
                                  d.privacy_class, coalesce(d.valid_from, d.created_at) said, d.valid_to, d.created_at,
                                  d.attributes->>'start' start_at, d.attributes->>'network' network,
                                  (d.attributes->>'messages')::int msgs, (d.attributes->>'owner_messages')::int own,
                                  d.attributes->>'agreed' agreed, d.lineage_id::text lineage,
                                  (select max(ch.at) from core.derived_changes ch where ch.item_id = d.item_id
                                   and ch.op in ('supersede', 'reconcile', 'contest') and ch.reverted_at is null) changed_at
                           from core.derived_items d
                           where d.subject_entity_ids @> array[%s::uuid] and d.generation = 'g1'
                             and d.status in ('derived', 'verified', 'superseded', 'retracted')
                             and (%s::timestamptz is null or d.created_at <= %s)""", (eid, at, at)).fetchall()
    now = at or datetime.now(timezone.utc)
    out = {"conversations": [], "plans": [], "statements": [], "history": [], "withheld": 0}
    for r in rows:
        if r["privacy_class"] not in allowed:
            out["withheld"] += 1
            continue
        gone = r["status"] in ("superseded", "retracted")
        if gone and at is not None and (r["changed_at"] is None or r["changed_at"] > at):
            gone = False                    # replaced after the date asked: current then
        expired = r["valid_to"] is not None and r["valid_to"] <= now
        if r["derived_by"] == "flows.conversations":
            if not gone:
                out["conversations"].append(dict(r))
            continue
        if cloud and _sensitive(r["content"] or ""):
            out["withheld"] += 1
            continue
        line = {"id": r["id"], "text": _redact(r["content"], cloud), "kind": r["kind"], "stage": r["stage"],
                "who": WHO_ITEM.get(r["epistemic"] or "", "?"), "said": r["said"], "recorded": r["created_at"],
                "start": _ts(r["start_at"]), "agreed": r["agreed"] in ("true", "True", "1")}
        if gone or expired:
            out["history"].append({**line, "until": r["changed_at"] or r["valid_to"],
                                   "how": "expiré" if expired and not gone else
                                          "remplacé" if r["status"] == "superseded" else "retiré"})
        elif (r["derived_by"] == "episodic.plans" or r["kind"] in ("plan", "commitment", "goal")) \
                and r["stage"] not in ("executed", "done"):     # a carried-out action is a past fact, not a plan
            out["plans"].append(line)
        else:
            out["statements"].append(line)
    return out


def _day(d) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def state(key_or_id: str, *, at: datetime | str | None = None, max_privacy: str = "cloud_allowed", conn=None) -> dict:
    """The relational state of one person (or the candidates when the name is ambiguous)."""
    t0 = time.perf_counter()
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    now = at or datetime.now(timezone.utc)
    allowed, cloud = _allowed(max_privacy), max_privacy != "local_only"
    audience = "cloud_model" if cloud else "owner_local"
    stack = contextlib.ExitStack()
    if conn is None:
        conn = stack.enter_context(connection())
    with stack:
        who = resolve(conn, key_or_id)
        if "entity" not in who:
            who["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return who
        e = who["entity"]
        eid = e["entity_id"]
        from . import read_policy
        card = {}
        if e["kardex_contact_id"] is not None:
            fields = read_policy.CONTACT_FIELDS[audience]
            card = dict(conn.execute(f"select {', '.join(fields)} from kardex.contacts where id = %s",
                                     (e["kardex_contact_id"],)).fetchone() or {})
            if cloud:      # free text fields of the card: the same screen as claims
                card = {k: v for k, v in card.items() if not (isinstance(v, str) and _sensitive(v))}
        base = {r["window_name"]: dict(r) for r in conn.execute(
            "select * from kardex.relationship_baselines where entity_id = %s", (eid,)).fetchall()}
        devs = conn.execute("""select distinct on (metric) metric, baseline, current, baseline_window, current_window,
                                      sample_size, detected_on from kardex.communication_deviations
                               where entity_id = %s and acknowledged_at is null and detected_on >= %s
                                 and detected_on <= %s
                               order by metric, detected_on desc""",
                            (eid, (now - RECENT).date(), now.date())).fetchall()
        rels = conn.execute("""select r.predicate, o.entity_type, o.canonical_name, o.attributes->>'network' network,
                                      r.privacy_class, r.valid_from
                               from core.relationships r join core.entities o on o.entity_id = r.object_id
                               where r.subject_id = %s and r.predicate in ('works_on', 'member_of')
                                 and (r.valid_to is null or r.valid_to > %s)""", (eid, now)).fetchall()
        eps = conn.execute("""select view_key, title, privacy_class, last_at from views.view
                              where kind = 'episode' and %s::uuid = any(entity_ids) and status = 'active'
                              order by last_at desc nulls last limit 10""", (eid,)).fetchall()
        loops = []
        if e["kardex_contact_id"] is not None:
            loops = [dict(r, origin="boucle") for r in conn.execute(
                """select loop_type kind, description text, opened_at said, deadline_at due, status
                   from kardex.open_loops where contact_id = %s and status = 'open'""", (e["kardex_contact_id"],))]
            loops += [dict(r, origin="action") for r in conn.execute(
                """select action_type kind, description text, created_at said, due_date::timestamptz due, status
                   from kardex.actions where contact_id = %s and status in ('pending', 'open')""",
                (e["kardex_contact_id"],))]
            dates = conn.execute("""select event_type kind, title text, event_date, is_recurring from kardex.events
                                    where contact_id = %s and status is distinct from 'cancelled'
                                      and event_type in ('birthday', 'meeting', 'plan', 'life_event')""",
                                 (e["kardex_contact_id"],)).fetchall()
        else:
            dates = []
        claims = _claims(conn, e["kardex_contact_id"], audience, at, cloud)
        items = _items(conn, eid, at, allowed, cloud)
    # Kardex loops/actions/dates have no privacy class: screened like claims for a cloud reader
    hidden = 0
    if cloud:
        keep = [x for x in loops if not _sensitive(x["text"] or "")]
        hidden += len(loops) - len(keep)
        loops = [{**x, "text": _redact(x["text"], True)} for x in keep]
        dates = [d for d in dates if d["kind"] == "birthday" or not _sensitive(d["text"] or "")]
    convs = items["conversations"]
    recent = [c for c in convs if c["said"] and now - RECENT <= c["said"] <= now]
    contexts = {"projects": sorted({r["canonical_name"] for r in rels if r["predicate"] == "works_on"
                                    and (r["privacy_class"] or "cloud_allowed") in allowed}),
                "groups": [r for r in rels if r["predicate"] == "member_of"],
                "episodes": [dict(x) for x in eps if x["privacy_class"] in allowed],
                "episodes_withheld": sum(x["privacy_class"] not in allowed for x in eps)}
    follow = _follow_up(loops, items["plans"], dates, convs, now)
    out = {"key": f"person:{eid}", "name": e["canonical_name"], "entity_id": eid, "at": at, "now": now,
           "allowed": allowed, "identity": {"networks": sorted(e["networks"] or []), "card": card,
                                            "kardex": e["kardex_contact_id"] is not None},
           "claims": claims, "items": items, "loops": loops, "dates": dates, "baselines": base,
           "deviations": [dict(d) for d in devs], "recent": recent, "contexts": contexts, "follow_up": follow,
           "withheld": claims["withheld"] + items["withheld"] + hidden + contexts["episodes_withheld"],
           "measures_now_only": at is not None,
           "ms": round((time.perf_counter() - t0) * 1000, 1)}
    return out


def _follow_up(loops, plans, dates, convs, now) -> list[dict]:
    """What MAY call for a follow-up — a reading, never a task, a notification or an action."""
    out = []
    last_ex = max((c["said"] for c in convs if c["said"] and c["said"] <= now), default=None)
    for x in loops:
        due = x.get("due")
        if due and due <= now:
            out.append({"why": f"échéance passée le {P._d(due)}", "text": x["text"], "origin": x["origin"]})
        elif due and due <= now + SOON:
            out.append({"why": f"échéance le {P._d(due)}", "text": x["text"], "origin": x["origin"]})
    for p in plans:
        st = p.get("start")
        if not st:
            continue
        if now <= st <= now + SOON:
            out.append({"why": f"prévu le {P._d(st)}" + ("" if p["agreed"] else " (proposé, pas convenu)"),
                        "text": p["text"], "origin": "plan"})
        elif now - timedelta(days=30) <= st < now - QUIET_PLAN and (last_ex is None or last_ex < st):
            out.append({"why": f"prévu le {P._d(st)} : aucun échange depuis, tenu ou non inconnu", "text": p["text"],
                        "origin": "plan"})
    for d in dates:
        if not d["event_date"]:
            continue
        when = datetime(now.year, d["event_date"].month, d["event_date"].day, tzinfo=timezone.utc) \
            if d["kind"] == "birthday" else datetime.combine(d["event_date"], datetime.min.time(), timezone.utc)
        if d["kind"] == "birthday" and when < now - timedelta(days=1):
            when = when.replace(year=now.year + 1)
        if now - timedelta(days=1) <= when <= now + SOON:
            out.append({"why": f"{'anniversaire' if d['kind'] == 'birthday' else 'date'} le {P._d(when)}",
                        "text": None if d["kind"] == "birthday" else d["text"], "origin": "date"})
    return out


# ───────────────────────────── rendering ─────────────────────────────
FLOOR = {"identity": 2, "relation": 3, "changes": 2, "exchanges": 2, "commitments": 2, "follow_up": 2,
         "contexts": 1, "rhythm": 2, "history": 1}
ORDER = ("identity", "relation", "follow_up", "commitments", "changes", "exchanges", "contexts", "rhythm", "history")


def _id(i: str) -> str:
    return i if i.startswith("k") else i[:8]


def _l(x: dict, n: int = 110) -> str:
    sens = " · ne pas répéter à un tiers" if x.get("sensitive") else ""
    return f"- « {P._short(x['text'] or '', n)} » ({P._d(x['said'])} · {x['who']}{sens} · {_id(x['id'])})"


def _pct(v) -> str:
    return f"{round(100 * v)} %" if v is not None else "?"


def _dur(s) -> str:
    if s is None:
        return "?"
    return f"{round(s / 60)} min" if s < 3600 else f"{round(s / 3600, 1)} h" if s < 86400 else f"{round(s / 86400, 1)} j"


def blocks(s: dict) -> dict:
    now, b = s["now"], {}
    idt, cl, it = s["identity"], s["claims"], s["items"]
    card = idt["card"]
    il = [(f"- joignable sur : {', '.join(idt['networks']) or 'aucun compte relié'}"
           + ("" if idt["kardex"] else " ; pas de fiche Kardex"), None)]
    fields = [f"{lab} : {card[k]}" for k, lab in (("relationship_type", "relation (fiche)"),
                                                  ("relationship_status", "statut (fiche)"),
                                                  ("occupation", "activité"), ("languages", "langues"),
                                                  ("interests", "intérêts"), ("location_current", "lieu"))
              if card.get(k)]
    if fields:
        il.append((f"- fiche Kardex : {P._short(' ; '.join(str(f) for f in fields), 200)}", None))
    # the relation by who says it: confirmed, his own word, data, the person's word, hypotheses
    rank = {"confirmé par Monsieur": 0, "dit par Monsieur": 1, "vérifié par les données": 2, "source publique": 3,
            "observé dans les échanges": 4, "dit par la personne": 5, "rapporté par W.Alter": 6,
            "hypothèse, non vérifiée": 7}
    order = lambda xs: sorted(xs, key=lambda x: (rank.get(x["who"], 9), -x["said"].timestamp()))  # noqa: E731
    who_is = order([x for x in cl["current"] if IDENTITY_TYPE.search(x.get("type") or "")])
    il += [(_l(x, 90), x["id"]) for x in who_is[:4]]
    b["identity"] = ("Qui", il, [])
    lines = order([x for x in cl["current"] if x not in who_is] + it["statements"])
    said = [x for x in lines if x["who"] == "dit par la personne"]
    lines = [x for x in lines if x["who"] != "dit par la personne"] + said[:PERSON_LINES]
    rl = [(_l(x), x["id"]) for x in lines]
    a = s["baselines"].get("all") or {}
    if a.get("messages"):
        rl.insert(0, (f"- {a['messages']} messages échangés du {P._d(a['first_contact'])} au {P._d(a['last_contact'])} "
                      f"(vérifié par les données)", None))
    tail = []
    if cl["pending"]:
        tail.append(f"- {cl['pending']} informations dites par la personne, non confirmées par Monsieur")
    if s["withheld"]:
        tail.append(f"- {s['withheld']} éléments locaux ou sensibles, non transmis")
    b["relation"] = ("Relation connue (par qui le dit)", rl or [("- rien de connu au-delà des échanges", None)], tail)
    since = now - RECENT
    new = [x for x in cl["current"] + it["statements"] + it["plans"] if x["recorded"] and since <= x["recorded"] <= now]
    gone = [x for x in cl["history"] + it["history"] if x.get("until") and since <= x["until"] <= now]
    cl_ = []
    if new:
        by: dict[str, int] = {}
        for x in new:
            by[x["who"]] = by.get(x["who"], 0) + 1
        cl_.append((f"- {len(new)} informations nouvelles (" + ", ".join(f"{n} {w}" for w, n in by.items())
                    + f"), la dernière le {P._d(max(x['recorded'] for x in new))}", None))
    if gone:
        cl_.append((f"- {len(gone)} informations remplacées, retirées ou expirées (voir l'historique), la dernière le "
                    f"{P._d(max(x['until'] for x in gone))}", None))
    rels_new = [g for g in s["contexts"]["groups"] if g.get("valid_from") and since <= g["valid_from"] <= now]
    if rels_new:
        cl_.append((f"- {len(rels_new)} nouveaux groupes en commun", None))
    b["changes"] = (f"Changé ces {RECENT.days} derniers jours", cl_ or [("- rien de nouveau", None)], [])
    rc = s["recent"]
    el = []
    if rc:
        nets = sorted({c["network"] for c in rc if c["network"]})
        msgs, own = sum(c["msgs"] or 0 for c in rc), sum(c["own"] or 0 for c in rc)
        el.append((f"- {len(rc)} conversations en {RECENT.days} jours ({', '.join(nets) or '?'}), {msgs} messages dont "
                   f"{own} de Monsieur ; dernière {P._d(max(c['said'] for c in rc))}", None))
    elif s["items"]["conversations"]:
        last = max(c["said"] for c in s["items"]["conversations"] if c["said"])
        el.append((f"- aucune conversation en {RECENT.days} jours ; dernière le {P._d(last)}", None))
    else:
        el.append(("- aucune conversation relevée", None))
    b["exchanges"] = ("Échanges (mesures, jamais leur contenu)", el, [])
    cm = [(f"- [{'convenu' if p['agreed'] else 'proposé'}{', le ' + P._d(p['start']) if p.get('start') else ''}] "
           f"{_l(p, 95)[2:]}", p["id"]) for p in sorted(it["plans"], key=lambda p: -(p.get("start") or p["said"]).timestamp())]
    cm += [(f"- [{'à faire' if x['origin'] == 'action' else 'question ouverte'} (Kardex), "
            f"{'échéance ' + P._d(x['due']) if x.get('due') else 'sans échéance'}] « {P._short(x['text'] or '', 90)} » "
            f"(noté le {P._d(x['said'])})", None) for x in sorted(s["loops"], key=lambda x: -(x["said"] or now).timestamp())]
    b["commitments"] = ("Engagements et échanges en cours", cm or [("- aucun engagement connu", None)], [])
    fu = [(f"- {x['why']}" + (f" : « {P._short(x['text'], 80)} »" if x.get("text") else ""), None) for x in s["follow_up"]]
    if fu:
        b["follow_up"] = ("À suivre éventuellement (lecture seule : rien n'est créé ni envoyé)", fu, [])
    cx = s["contexts"]
    xl = []
    if cx["projects"]:
        xl.append((f"- projets : {', '.join(cx['projects'][:6])}", None))
    if cx["groups"]:
        nets = {}
        for g in cx["groups"]:
            nets[g["network"] or "?"] = nets.get(g["network"] or "?", 0) + 1
        local = "local_only" in s["allowed"]
        names = f" ({', '.join(P._short(g['canonical_name'] or '', 30) for g in cx['groups'][:4])})" if local else ""
        xl.append((f"- {len(cx['groups'])} groupes en commun : " + ", ".join(f"{n} {k}" for k, n in nets.items())
                   + names, None))
    for ep in list({(e["title"] or ""): e for e in reversed(cx["episodes"])}.values())[::-1][:2]:
        xl.append((f"- épisode : « {P._short(ep['title'] or '', 70)} » ({P._d(ep['last_at'])})", None))
    if xl:
        b["contexts"] = ("Contextes (une seule personne, plusieurs contextes)", xl, [])
    bl = s["baselines"]
    rh = []
    m30, m90 = bl.get("30d") or {}, bl.get("90d") or {}
    if m30 or m90:
        rh.append((f"- 30 j : {m30.get('messages', 0)} messages ({_pct(m30.get('initiation_ratio_me'))} lancés par "
                   f"Monsieur) ; 90 j : {m90.get('messages', 0)} ; délai médian de réponse : Monsieur "
                   f"{_dur(m90.get('median_reply_me_s'))}, la personne {_dur(m90.get('median_reply_them_s'))}", None))
    for d in s["deviations"]:
        lab, f = METRICS.get(d["metric"], (d["metric"], "{:.2f}"))
        fmt = (lambda v: _pct(v)) if f == "%" else (lambda v: _dur(v)) if f == "s" else (lambda v, f=f: f.format(v))
        rh.append((f"- écart mesuré : {lab} {fmt(d['baseline'])} → {fmt(d['current'])} ({d['current_window']} vs "
                   f"{d['baseline_window']}, relevé le {P._d(_day(d['detected_on']))})", None))
    if rh:
        b["rhythm"] = ("Rythme mesuré", rh, ["- des mesures, cause inconnue : aucune conclusion sur la personne ou la "
                                             "relation"] + (["- mesures actuelles (pas d'historique à la date demandée)"]
                                                            if s.get("measures_now_only") else []))
    hi = sorted(cl["history"] + it["history"], key=lambda x: -(x.get("until") or x["said"]).timestamp())
    if hi:
        b["history"] = ("Historique (informations remplacées, conservées)",
                        [(f"- {x['how']} le {P._d(x.get('until') or x['said'])} : « {P._short(x['text'] or '', 90)} » "
                          f"({x['who']} · {_id(x['id'])}"
                          + (f" → {_id(x['replaced_by'])}" if x.get("replaced_by") else "") + ")", x["id"])
                         for x in hi], [])
    return b


def render(s: dict, max_tokens: int = 900) -> tuple[str, list[str]]:
    from .personal import _fit
    if "ambiguous" in s:
        lines = [f"« {s['name']} » désigne {len(s['ambiguous'])} personnes connues (jamais fusionnées) — préciser :"]
        for c in s["ambiguous"]:
            lines.append(f"- person:{c['entity_id'][:8]} : {', '.join(sorted(c['networks'] or [])) or 'sans compte'}, "
                         f"{c['messages']} messages" + (f", dernier échange {P._d(c['last_contact'])}"
                                                         if c.get("last_contact") else "")
                         + (" ; fiche Kardex" if c.get("kardex_contact_id") is not None else ""))
        return "\n".join(lines), []
    if "missing" in s:
        return f"Personne inconnue : « {s['missing']} » (person_lookup pour chercher)", []
    when = f"au {P._d(s['at'])}" if s.get("at") else "maintenant"
    head = (f"Relation avec {s['name']} — {when} (chaque ligne datée, avec qui la dit"
            + ("" if "local_only" in s["allowed"] else " ; rien de local ni de sensible vers un modèle cloud") + ").")
    foot = f"Plus : memory_view(key=\"person:{s['entity_id'][:8]}\", depth=\"state\") ; person_lookup ; memory_search."
    budget = max_tokens - P._tokens(head) - P._tokens(foot)
    body, shown = _fit(blocks(s), ORDER, budget)
    return "\n".join([head, *body, foot]), list(dict.fromkeys(shown))


def read(q: dict) -> dict:
    """memory_view depth="state" for key person:<name or id> (MemoryViewQuery v1 shape)."""
    s = state(q["key"], at=q.get("at"), max_privacy=q.get("privacy") or "cloud_allowed")
    text, shown = render(s, int(q.get("max_tokens") or 900))
    return {"key": s.get("key") or q["key"], "depth": "state", "version": None, "content": text,
            "built_at": datetime.now(timezone.utc), "watermark": None, "stale": False, "sources": shown,
            "deeper": ["history"], "at": q.get("at"), "ms": s.get("ms"),
            **({"ambiguous": [c["entity_id"] for c in s["ambiguous"]]} if "ambiguous" in s else {})}


def check(keys: list[str], *, limit_ms: float = 50.0) -> dict:
    """Invariants on real people, by aggregates (no content in the result): nothing local or sensitive cited for a
    cloud reader, nothing replaced cited as current, every cited item about that person, latency under limit_ms."""
    out = []
    for k in keys:
        state(k)                                  # warm
        s = state(k)
        if "ambiguous" in s or "missing" in s:
            out.append({"key": k, "resolved": "ambiguous" if "ambiguous" in s else "missing",
                        "candidates": len(s.get("ambiguous") or []), "ms": s["ms"]})
            continue
        text, shown = render(s)
        problems = []
        ids = [i for i in shown if not i.startswith("k")]
        with connection() as conn:
            rows = conn.execute("""select item_id::text id, status, privacy_class, %s::uuid = any(subject_entity_ids) about
                                   from core.derived_items where item_id = any(%s::uuid[])""",
                                (s["entity_id"], ids)).fetchall()
            kc = conn.execute("""select id, status, sensitivity, mention_policy, disclosure_state from kardex.claims
                                 where id = any(%s)""", ([int(i[1:]) for i in shown if i.startswith("k")],)).fetchall()
        hist = {x["id"] for x in s["claims"]["history"] + s["items"]["history"]}
        for r in rows:
            if r["privacy_class"] == "local_only":
                problems.append("élément local cité pour un lecteur cloud")
            if r["status"] not in ("derived", "verified") and r["id"] not in hist:
                problems.append("élément remplacé cité comme courant")
            if not r["about"]:
                problems.append("élément d'une autre personne")
        for c in kc:
            if c["sensitivity"] in ("sensitive", "highly_sensitive") or c["disclosure_state"] == "restricted":
                problems.append("affirmation sensible citée pour un lecteur cloud")
            if c["status"] not in ("active", "confirmed", "proposed") and f"k{c['id']}" not in hist:
                problems.append("affirmation remplacée citée comme courante")
        if s["ms"] > limit_ms:
            problems.append(f"latence {s['ms']} ms > {limit_ms} ms")
        out.append({"key": k, "ok": not problems, "ms": s["ms"], "tokens": P._tokens(text), "cited": len(shown),
                    "claims": len(s["claims"]["current"]), "history": len(s["claims"]["history"]) +
                    len(s["items"]["history"]), "conversations": len(s["items"]["conversations"]),
                    "plans": len(s["items"]["plans"]), "follow_up": len(s["follow_up"]),
                    "projects": len(s["contexts"]["projects"]), "groups": len(s["contexts"]["groups"]),
                    "withheld": s["withheld"], "problems": sorted(set(problems))})
    return {"people": out, "ok": all(x.get("ok", True) for x in out)}
