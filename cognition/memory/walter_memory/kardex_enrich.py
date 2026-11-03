"""Kardex enrichment from the owner's conversations (Memory V1, 2026-11-03): what a contact said about THEMSELVES.

For one person (a core.entities person with Beeper / Gmail identities), the recent 1:1 messages (redacted_cloud only:
local_only conversations are never sent) are PSEUDONYMISED and read once by the Router's memory_extraction poste,
which returns claims about the contact: work, city, languages, interests, plans, preferences, family, health…
Each claim is checked and stored by the code, not the model:
  * only what the CONTACT states or clearly shows about themselves — never the owner's own information (his
    plans, health, places, money): a contact's card must not carry the owner's private life;
  * status `proposed` (unconfirmed: shown as such), knowledge_origin direct_statement, disclosure explicitly_told_me;
  * sensitivity from the model, tightened by the claim type (health, sexuality, religion, politics, money, legal →
    highly_sensitive / sensitive) and the mention policy follows from it (normal → free, personal → contextual_only,
    sensitive and above → never_reference): read_policy then decides per audience, as for every claim;
  * evidence rows with the exact quote and the canonical event id; a claim already known (local similarity ≥ 0.9)
    gains evidence instead of a duplicate.
Fed only by this walter-memory processor from core.events (A10). Capped per run; the cost is the Router's.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from . import organic, privacy
from .db import connection

log = logging.getLogger("walter.kardex")
METHOD = "walter_memory.kardex_enrich@1"
SENSITIVE_TYPES = {"health": "highly_sensitive", "sexual_preference": "highly_sensitive", "sexuality": "highly_sensitive",
                   "religion": "sensitive", "politics": "sensitive", "money": "sensitive", "finance": "sensitive",
                   "legal": "sensitive", "family_conflict": "sensitive"}
POLICY = {"normal": "free", "personal": "contextual_only", "sensitive": "never_reference",
          "highly_sensitive": "never_reference"}
PROMPT = """Messages entre Monsieur (le propriétaire) et un contact, pseudonyme {who}. Les autres noms sont aussi
pseudonymisés : garde les pseudonymes tels quels.

{messages}

Relève ce que {who} dit ou montre clairement SUR LUI-MÊME OU ELLE-MÊME (métier, ville, langues, centres d'intérêt,
projets, préférences, habitudes, famille, santé…). Ne relève RIEN sur Monsieur : ni ses projets, ni sa santé, ni ses
lieux, ni son argent. Pas d'interprétation psychologique. Réponds en JSON :
{{"claims": [{{"claim": "une affirmation autonome sur {who}, en français", "type": "work|location|language|interest|plan|
preference|routine|family|relationship_history|health|money|religion|politics|legal|other",
"sensitivity": "normal|personal|sensitive|highly_sensitive", "msgs": [numéros], "quote": "extrait exact 3-20 mots",
"confidence": 0.0}}]}}"""


def settings() -> dict:
    return {"per_run": 5, "days": 60, "max_messages": 160, **(organic.settings().get("kardex") or {})}


def contact_for(conn, entity_id: str) -> int:
    e = conn.execute("select canonical_name, kardex_contact_id from core.entities where entity_id = %s", (entity_id,)).fetchone()
    if e["kardex_contact_id"] is not None:
        return e["kardex_contact_id"]
    cid = conn.execute("""insert into kardex.contacts (canonical_name, sources, identity_status, created_at, updated_at)
                          values (%s, %s, 'linked', now(), now()) returning id""",
                       (e["canonical_name"], ["walter_memory"])).fetchone()["id"]
    conn.execute("update core.entities set kardex_contact_id = %s, updated_at = now() where entity_id = %s", (cid, entity_id))
    return cid


def messages_with(conn, entity_id: str, days: int, limit: int) -> list[dict]:
    """The owner's 1:1 messages with this person (both directions), redacted_cloud only, most recent first."""
    return conn.execute("""
        with threads as (
            select distinct e.thread_id from core.events e join core.identity_links l on l.identity_id = e.actor_identity_id
            where l.entity_id = %s and e.source in ('beeper', 'gmail') and e.occurred_at > now() - make_interval(days => %s)
              and coalesce(e.payload->'chat'->>'type', 'single') <> 'group')
        select e.event_id::text, e.event_type, e.occurred_at, e.content, e.privacy_class,
               (l.entity_id = %s) as from_contact
        from core.events e left join core.identity_links l on l.identity_id = e.actor_identity_id
        where e.thread_id in (select thread_id from threads) and e.occurred_at > now() - make_interval(days => %s)
          and e.event_type in ('message.sent', 'message.received', 'email.sent', 'email.received')
          and e.privacy_class = any(%s) and coalesce(e.content, '') <> ''
          and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                          and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
        order by e.occurred_at desc limit %s""", (entity_id, days, entity_id, days, privacy.model_classes(), limit)).fetchall()


def enrich(entity_id: str, *, chat=None, days: int | None = None, max_messages: int | None = None) -> dict:
    from . import llm
    from .search import embed
    chat = chat or llm.chat
    st = settings()
    days, max_messages = days or st["days"], max_messages or st["max_messages"]
    with connection() as conn:
        name = conn.execute("select canonical_name from core.entities where entity_id = %s", (entity_id,)).fetchone()["canonical_name"]
        msgs = list(reversed(messages_with(conn, entity_id, days, max_messages)))
    if len([m for m in msgs if m["from_contact"]]) < 3:
        return {"entity": entity_id, "skipped": "too few messages from the contact"}
    who = name if not privacy.pseudonymise() else "Contact"     # real names when pseudonymisation is off
    lines = "\n".join(f"{k}. [{m['occurred_at']:%d/%m/%Y}] {who if m['from_contact'] else 'Monsieur'} : "
                      f"{privacy.mask_secrets(m['content'] or '')[:500]}" for k, m in enumerate(msgs, 1))
    from . import processing
    cls = privacy.strictest(*(m["privacy_class"] for m in msgs))
    prompt = PROMPT.format(who=who, messages=lines[:24000])

    def call():
        res = chat([{"role": "user", "content": prompt}], poste="memory_extraction",
                   processor="kardex.enrich", processor_version="1", privacy_class=cls, names=[name],
                   budget="recurring", purpose="kardex: what a contact says about themselves",
                   response_format={"type": "json_object"}, max_tokens=2500, timeout=240)
        c = res["content"] or "{}"
        return {"data": json.loads(c[c.find("{"):c.rfind("}") + 1] or "{}"), "model": res.get("model")}, res.get("model")

    # the same messages were already read (2026-11-03): their claims are recorded, nothing to ask again
    got, reused = processing.decide_once("kardex.enrich", "1", {"prompt": prompt, "names": [name], "class": cls}, call,
                                         privacy_class=cls, refs=[m["event_id"] for m in msgs if m.get("event_id")],
                                         input_key=entity_id)
    if reused:
        return {"entity": entity_id, "skipped": "no new message since the last reading"}
    data = got["data"]
    out = {"entity": entity_id, "messages": len(msgs), "claims": 0, "reused": 0, "rejected": 0, "model": got.get("model")}
    with connection() as conn:
        cid = contact_for(conn, entity_id)
        known = conn.execute("select id, claim from kardex.claims where contact_id = %s", (cid,)).fetchall()
        kv = embed([k["claim"][:300] for k in known]) if known else None
        for it in data.get("claims") or []:
            text = str(it.get("claim") or "").strip()
            cited = [msgs[i - 1] for i in it.get("msgs") or [] if isinstance(i, int) and 1 <= i <= len(msgs)]
            quote = str(it.get("quote") or "").strip()
            src = [m for m in cited if m["from_contact"]]
            if not text or not src or not any(_norm(quote)[:40] in _norm(m["content"]) for m in cited if quote):
                out["rejected"] += 1                       # no message of the contact, or a quote not found
                continue
            ctype = str(it.get("type") or "other")[:40]
            sens = str(it.get("sensitivity") or "personal")
            sens = sens if sens in POLICY else "personal"
            floor = SENSITIVE_TYPES.get(ctype)
            if floor and list(POLICY).index(floor) > list(POLICY).index(sens):
                sens = floor
            if kv is not None:
                v = embed([text[:300]])[0]
                sims = kv @ v
                j = int(sims.argmax())
                if float(sims[j]) >= 0.9:
                    _evidence(conn, cid, known[j]["id"], src[0], quote, sens)
                    out["reused"] += 1
                    continue
            claim_id = conn.execute("""insert into kardex.claims (contact_id, claim_type, category, claim, claim_json, status,
                                           confidence, valid_from, extraction_method, metadata, knowledge_origin,
                                           disclosure_state, mention_policy, sensitivity, owner_knows, contact_told_owner)
                                       values (%s, %s, %s, %s, %s, 'proposed', %s, %s, %s, %s, 'direct_statement',
                                               'explicitly_told_me', %s, %s, true, true) returning id""",
                                    (cid, ctype, ctype, text, json.dumps(it, ensure_ascii=False), _conf(it),
                                     src[0]["occurred_at"], METHOD, json.dumps({"model": got.get("model"),
                                                                                "event_ids": [m["event_id"] for m in src]}),
                                     POLICY[sens], sens)).fetchone()["id"]
            _evidence(conn, cid, claim_id, src[0], quote, sens)
            out["claims"] += 1
    return out


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def _conf(it) -> float:
    try:
        return max(0.0, min(1.0, float(it.get("confidence") or 0.6)))
    except (TypeError, ValueError):
        return 0.6


def _evidence(conn, contact_id: int, claim_id: int, msg: dict, quote: str, sens: str) -> None:
    eid = conn.execute("""insert into kardex.evidence (contact_id, source, source_ref, timestamp, speaker, quote,
                              evidence_type, confidence, metadata, knowledge_origin, sensitivity, acquired_at)
                          values (%s, 'core.events', %s, %s, 'contact', %s, 'message', 0.8, %s, 'direct_statement', %s, now())
                          returning id""",
                       (contact_id, msg["event_id"], msg["occurred_at"], quote[:500], json.dumps({"method": METHOD}),
                        sens)).fetchone()["id"]
    conn.execute("insert into kardex.claim_evidence (claim_id, evidence_id, role, weight) values (%s, %s, 'supports', 1.0)",
                 (claim_id, eid))


def top_contacts(limit: int = 5, days: int = 30) -> list[str]:
    """The people the owner exchanged with most in 1:1 recently (Kardex baselines + V1 relations)."""
    with connection() as conn:
        rows = conn.execute("""select r.object_id::text eid, sum(coalesce(array_length(r.source_event_ids, 1), 0)) n
                               from core.relationships r
                               join core.entities e on e.entity_id = r.object_id and e.entity_type = 'person'
                               where r.predicate = 'exchanged_with' and r.generation = 'g1'
                                 and r.privacy_class = 'redacted_cloud'
                                 and (r.attributes->>'last_at')::timestamptz > now() - make_interval(days => %s)
                               group by 1 order by 2 desc limit %s""", (days, limit * 3)).fetchall()
    return [r["eid"] for r in rows][:limit]


def run(limit: int | None = None) -> dict:
    limit = limit or settings()["per_run"]
    out = []
    for eid in top_contacts(limit):
        try:
            out.append(enrich(eid))
        except Exception as e:  # noqa: BLE001
            out.append({"entity": eid, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    return {"contacts": len(out), "claims": sum(r.get("claims", 0) for r in out),
            "reused": sum(r.get("reused", 0) for r in out), "results": [{k: v for k, v in r.items() if k != "entity"}
                                                                        for r in out]}
