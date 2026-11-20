"""Knowledge extraction v2 (Memory V1, 2026-11-02): incremental, every runtime, strict provenance, supersession.

What it does. Conversations with W.Alter in any runtime (Hermes and its profiles, Claude Code, Codex, DSH, and any
runtime added to RUNTIMES) are read from core.events per thread. Coverage is tracked per canonical event
(extraction.covered): a thread that keeps going gets new segments, a late event is simply "not covered yet". A
segment is processed when its thread has been quiet for IDLE, when it holds SEGMENT_CHARS, or when its oldest event
has waited MAX_WAIT (long sessions never wait for their end).

Per segment, one Router call (poste memory_extraction) returns atomic knowledge — fact, decision, preference, goal,
constraint, commitment, correction — each citing message numbers and an exact quote. Kept only when:
  - every cited number exists in the segment (no fallback to "the whole segment": an item without valid citations
    is rejected and recorded in extraction.segments.rejected),
  - the quote is found in a cited message,
  - owner kinds (decision, preference, goal, constraint, correction) cite at least one message of the owner.
An item may restate a known one (same_as → the known item gets the new evidence, no duplicate), supersede it (the
old one becomes 'superseded', valid_to set: Context reads only current knowledge) or contradict it (both flagged
contested). Supersession needs the owner's word; otherwise it is recorded as a contradiction.

Never sent to a cloud model: local_only (and redacted_cloud, whose quotes cannot be verified) messages; they are
covered by a 'local_only_unavailable' segment, so they are not retried forever. Noise (injected context, automated
reviews, bench/lab runs) is covered as 'filtered' without any model call. Epistemic state is explicit: a decision is
proposed/decided/executed/abandoned, a commitment open/done, and attributes.epistemic says whether the owner stated
it or only the agent reported it (a decision taken is not an action done; a claim is not a truth).

Pre-V1 history: only events ingested after extraction.state['v1_start'] are eligible; older ones are processed only
on explicit request (`enqueue --since`), never by the sweep.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import llm, privacy
from .db import connection

log = logging.getLogger("walter.extract2")

PROCESSOR, VERSION = "l3.extract", "3"     # 3 = typed statements + reconciliation (lot 1, 2026-11-19)
POSTE = "memory_extraction"          # Walter Router poste: the router picks the model (never hardcoded)
RUNTIMES = ("hermes", "claude_code", "codex", "dsh", "walter")
MESSAGE_TYPES = ("message.sent", "message.received")    # sent = the owner, received = the assistant (or the contact)
# E2E 20/11 (owner: « l'extraction doit aussi traiter les messages entrants et sortants de mes contacts, y compris les
# transcriptions audio »): the owner's 1:1 conversations with his contacts go through the same extraction, the same
# reconciliation and the same write gate; received = the contact (a third party), never the assistant. Live only from
# extraction.state['contacts_start'] ([extraction] contacts = "single" | "off"): no automatic sweep of the history.
CONTACT_SOURCES = ("beeper",)
SOURCES = RUNTIMES + CONTACT_SOURCES
AWAIT_TEXT = timedelta(minutes=10)    # a voice note without its transcript yet is waited for this long
KINDS = ("fact", "decision", "preference", "goal", "constraint", "commitment", "correction")
OWNER_KINDS = {"decision", "preference", "goal", "constraint", "correction"}
# Stage of an intention (P1.2): a request is not a decision, a decision is not an execution, a report is not a proof.
STAGES = {"decision": {"requested", "proposed", "decided", "executed", "abandoned"},
          "goal": {"requested", "decided", "executed", "abandoned"}, "commitment": {"open", "done"}}
STATES = STAGES                     # P1.1 name
SCOPES = {"durable", "task", "until"}
# Lot 1 (2026-11-19): typed statements. type (what the model writes) → (stored kind, act). The kind keeps the readers'
# vocabulary (working state, views); the act says what kind of statement it is (attributes.act).
TYPES = {"fait": ("fact", "fact"), "preference": ("preference", "rule"), "contrainte": ("constraint", "rule"),
         "correction": ("correction", "correction"), "proposition": ("decision", "proposal"),
         "hypothese": ("fact", "hypothesis"), "decision": ("decision", "decision"), "objectif": ("goal", "goal"),
         "action": ("commitment", "action"), "resultat": ("fact", "result"), "etat": ("fact", "state"),
         "annulation": ("decision", "cancel")}
LEGACY_ACT = {"fact": "fact", "decision": "decision", "preference": "rule", "goal": "goal", "constraint": "rule",
              "commitment": "action", "correction": "correction"}
ACT_STAGES = {"action": {"annoncee": "open", "open": "open", "en_cours": "in_progress", "in_progress": "in_progress",
                         "terminee": "executed", "done": "executed", "executed": "executed"},
              "decision": {"decidee": "decided", "decided": "decided", "requested": "requested",
                           "executed": "executed", "abandoned": "abandoned", "abandonnee": "abandoned"},
              "goal": {"demande": "requested", "requested": "requested", "decided": "accepted", "accepted": "accepted",
                       "executed": "executed", "abandoned": "abandoned"}}
DOMAINS = {"personnel": "personal", "personal": "personal", "projet": "project", "project": "project",
           "tache": "task", "tâche": "task", "task": "task", "relation": "relation", "test": "test"}
OWNER_ACTS = {"rule", "correction", "goal", "cancel"}
SEGMENT_CHARS = 24000
MSG_CHARS = 3000
IDLE = timedelta(minutes=20)
MAX_WAIT = timedelta(hours=2)
LEASE = timedelta(minutes=15)
MAX_ATTEMPTS = 5
CONTEXT_MSGS = 4
KNOWN_THREAD, KNOWN_SIMILAR = 15, 10

AUTOMATED = re.compile(r"^\s*(The following is the Codex agent history|\{\s*\"risk_level\"|\[IMPORTANT: Background process|"
                       r"\[The user sent a voice message~? Here's what they said: \"\s*\"\])", re.S)
# Adaptive working memory (P1.1): an owner message that sets something interprets at once; the rest is grouped.
DIRECTIVE = re.compile(r"(?i)(\btu (peux|pourrais|dois)\b|peux[- ]tu|\b(fais|fait|refais|refait|cr[ée]e[rsz]?|ajoute|mets|installe|"
                       r"connecte|configure|corrige|r[ée]pare|supprime|envoie|r[ée]ponds|insiste|tourne|d[ée]dui[st]|utilise|"
                       r"passe|teste|analyse|v[ée]rifie|regarde|montre|explique|prends|continue|reprends|commence|mesure)\b)")
MARKERS = re.compile(r"(?i)(je valide|valid[eé]|on garde|on part sur|je veux|je ne veux|\bne (pas|jamais|plus)\b|jamais|"
                     r"toujours|désormais|dorénavant|finalement|plutôt|arr[eê]te|\bstop\b|décid|renomm|supprim|\bgarde|"
                     r"retire|oublie|priorit|d.abord|à partir de|il faut|faut (le|la|les|qu)|surtout|uniquement|interdit|"
                     r"oblig|n.envoie|envoi[es]?\b|commit|lance|vas[- ]?y)")
LONG_MESSAGE = 600
ADAPT_QUIET = timedelta(minutes=5)
ADAPT_TURNS = 3
# Text the runtime appends to an owner message (not his words): removed before reading and quoting.
RUNTIME_NOTES = re.compile(r"\[Your active task list was preserved across context compression\].*$", re.S)

PROMPT = """Tu extrais la mémoire d'un extrait de conversation entre Monsieur (le propriétaire) et son assistant W.Alter : des énoncés typés, pas un résumé.

Contexte qui précède (ne pas citer) :
{context}

Connaissances déjà enregistrées (références K) :
{known}
(elles servent à écrire chaque énoncé complet et à jour ; Walter rapproche lui-même les énoncés de ces connaissances)

Projets déjà connus (identifiants) : {projects}

Messages à analyser (numérotés, seuls citables) :
{transcript}

Rends un JSON :
{{"summary": "2 à 5 phrases : de quoi il a été question, ce qui a été décidé ou fait, où on en est",
  "topics": ["..."], "people": ["personnes citées hors Monsieur et W.Alter"],
  "items": [{{"type": "fait|preference|contrainte|correction|proposition|hypothese|decision|objectif|action|resultat|etat|annulation",
              "text": "un seul énoncé, autonome et compréhensible sans la conversation ; s'il met à jour une connaissance K, la version complète à jour",
              "author": "monsieur | walter | tiers",
              "domain": "personnel | projet | tache | relation | test",
              "project": "identifiant court du projet si domain = projet ou tache, sinon null",
              "stage": "action : annoncee|en_cours|terminee ; sinon null",
              "scope": "durable | task | until", "until": "AAAA-MM-JJ si scope = until ou si un état a une fin connue, sinon null",
              "about": "K… si l'énoncé porte sur une connaissance déjà enregistrée, sinon null",
              "msgs": [numéros des messages qui l'établissent],
              "quote": "extrait EXACT (copié mot pour mot, 5 à 25 mots) d'un des messages cités",
              "confidence": 0.0}}]}}

Types (un énoncé = un seul acte) :
- fait : une information déclarée ; author = qui l'affirme. Ce que W.Alter dit de l'état d'un système est un fait déclaré par W.Alter, pas un fait vérifié ;
- preference / contrainte : une règle, un goût, une manière de travailler, une limite que Monsieur pose (une question de Monsieur qui exprime clairement une attente est une contrainte) ;
- correction : Monsieur corrige une information ou une erreur ;
- proposition : une option proposée, rien n'est tranché ;
- hypothese : une supposition ou une explication probable, non vérifiée ;
- decision : Monsieur a décidé ou validé ; une approbation courte (« oui », « vas-y », « ok ») d'une proposition est une décision : écris-la complète et cite la proposition et l'approbation ;
- objectif : ce que Monsieur demande ou veut atteindre (« tu peux… », « analyse… », « fais… ») ; les étapes d'une même demande ne sont pas des objectifs séparés : un seul objectif par intention ;
- action : ce que quelqu'un s'engage à faire (annoncee), fait en ce moment (en_cours) ou dit avoir fait (terminee) — c'est un compte rendu, pas une preuve ;
- resultat : ce qui a été constaté à l'issue d'une action ou d'un contrôle (tests passés, mesure, sortie d'une commande, confirmation de Monsieur) : dis ce qui a été constaté et par quoi ;
- etat : un état passager (en panne, en pause, en cours de migration, en attente de…) ;
- annulation : Monsieur renonce à quelque chose, l'arrête ou l'annule.
Domaine, à décider pour CHAQUE énoncé (jamais d'après les projets cités ailleurs dans l'extrait) :
- personnel : vaut pour Monsieur lui-même (sa vie, ses goûts, sa manière générale de travailler avec W.Alter) ;
- projet : vaut pour un projet précis (code, architecture, choix, état d'un dépôt ou d'un module) ; project = l'identifiant de la chose dont parle l'énoncé (pour W.Alter : walter, ou walter-<module> comme walter-memory, walter-router, walter-context, walter-engine). Toute la conversation a lieu avec W.Alter : ce n'est jamais une raison de choisir walter. walter seulement si l'énoncé porte sur W.Alter lui-même ou un de ses modules ; un appareil, un compte, une démarche de Monsieur (sa télévision, sa boîte mail) ou un autre projet a son propre identifiant, ou le domaine personnel ;
- tache : ne vaut que pour le travail en cours (« attends mon accord avant l'étape suivante ») ;
- relation : une personne et son lien avec Monsieur ;
- test : données de test, essais, bancs, exemples fictifs (ils ne sont pas gardés).
Portée (scope) : durable = vaut au-delà du travail en cours ; task = ne vaut que pour le travail en cours ; until = jusqu'à une date.
Règles : uniquement ce qui est dit dans les messages numérotés ; une affirmation de W.Alter n'est ni une décision de Monsieur ni un fait vérifié ; une affirmation d'un tiers se dit « selon … » ; ne garde pas les détails passagers (commandes lancées, erreurs corrigées en route) sauf s'ils établissent une règle, une décision, un résultat ou un état ; listes vides si rien ; chaque énoncé cite ses numéros et une citation exacte."""
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:16]

# E2E 20/11: the same typed statements for a conversation between the owner and one of his contacts. Same JSON, same
# types, same reconciliation; what changes is who speaks and what a contact's words can establish.
PROMPT_CONTACT = """Tu extrais la mémoire d'un extrait de conversation privée entre Monsieur (le propriétaire) et son contact {contact} : des énoncés typés, pas un résumé.

Contexte qui précède (ne pas citer) :
{context}

Connaissances déjà enregistrées (références K) :
{known}
(elles servent à écrire chaque énoncé complet et à jour ; Walter rapproche lui-même les énoncés de ces connaissances)

Messages à analyser (numérotés, seuls citables ; une note vocale ou un document est donné par sa transcription) :
{transcript}

Rends un JSON :
{{"summary": "1 à 3 phrases : de quoi il a été question, ce qui a été dit, proposé ou convenu",
  "topics": ["..."], "people": ["personnes citées hors Monsieur et {contact}"],
  "items": [{{"type": "fait|preference|contrainte|correction|proposition|hypothese|decision|objectif|action|resultat|etat|annulation",
              "text": "un seul énoncé, autonome et compréhensible sans la conversation, qui nomme la personne ({contact}, Monsieur…) ; s'il met à jour une connaissance K, la version complète à jour",
              "author": "monsieur | contact",
              "about": "K… si l'énoncé porte sur une connaissance déjà enregistrée, sinon null",
              "who": "de qui parle l'énoncé : contact | monsieur | le nom d'une autre personne",
              "domain": "personnel | relation | projet | test",
              "stage": "action : annoncee|en_cours|terminee ; sinon null",
              "scope": "durable | until", "until": "AAAA-MM-JJ si l'énoncé ne vaut que jusqu'à une date connue, sinon null",
              "msgs": [numéros des messages qui l'établissent],
              "quote": "extrait EXACT (copié mot pour mot, 5 à 25 mots) d'un des messages cités",
              "confidence": 0.0}}]}}

Types (un énoncé = un seul acte) :
- fait : une information déclarée par celui qui parle (où il vit, son travail, un voyage prévu…) ; ce que dit {contact} est déclaré par {contact}, jamais vérifié ;
- etat : une situation passagère (malade, en déplacement, occupé jusqu'à…) ;
- proposition : une option proposée par l'un des deux (un rendez-vous, un café, une aide) : rien n'est tranché tant que l'autre ne l'a pas acceptée dans les messages ;
- action : ce que quelqu'un s'engage à faire (annoncee : « je te confirmerai », « je t'envoie ça demain »), fait en ce moment (en_cours) ou dit avoir fait (terminee) ;
- decision : seulement ce que Monsieur décide ou accepte lui-même ;
- objectif / preference / contrainte / correction / annulation : ceux de Monsieur seulement ; un souhait du contact est un fait déclaré par lui ;
- hypothese : une supposition, non vérifiée ; resultat : ce qui a été constaté.
Règles : uniquement ce qui est dit dans les messages numérotés ; une proposition sans réponse de Monsieur reste une proposition (jamais un rendez-vous accepté) ; une promesse de confirmer plus tard est une action annoncée de celui qui la fait ; un changement (« j'ai quitté Lyon, je vis à Paris ») s'écrit comme la nouvelle version complète, avec about = la connaissance K qu'il remplace ; les salutations, remerciements et banalités ne sont pas des énoncés ; listes vides si rien ; chaque énoncé cite ses numéros et une citation exacte."""
PROMPT_CONTACT_HASH = hashlib.sha256(PROMPT_CONTACT.encode()).hexdigest()[:16]


# ───────────────────────────── state ─────────────────────────────
def v1_start(conn) -> datetime | None:
    r = conn.execute("select value from extraction.state where key = 'v1_start'").fetchone()
    return datetime.fromisoformat(r["value"]["at"]) if r else None


def set_v1_start(at: datetime | None = None) -> str:
    at = at or datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute("""insert into extraction.state (key, value) values ('v1_start', %s)
                        on conflict (key) do update set value = excluded.value, updated_at = now()""",
                     (json.dumps({"at": at.isoformat()}),))
    return at.isoformat()


def live_start(conn) -> datetime | None:
    r = conn.execute("select value from extraction.state where key = 'live_start'").fetchone()
    return datetime.fromisoformat(r["value"]["at"]) if r else None


def set_live_start(at: datetime | None = None) -> str:
    """Production start of the continuous extraction (2026-11-19, owner: « réactive l'extraction continue sur les
    nouveaux événements », then the history by slices): the live worker takes messages ingested from this instant;
    what waited before it goes through backfill() in slices, under the per-segment Codex quota gate."""
    at = at or datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute("""insert into extraction.state (key, value) values ('live_start', %s)
                        on conflict (key) do update set value = excluded.value, updated_at = now()""",
                     (json.dumps({"at": at.isoformat()}),))
    return at.isoformat()


def channel(source: str) -> str:
    return "contact" if source in CONTACT_SOURCES else "agent"


def contacts_start(conn) -> datetime | None:
    r = conn.execute("select value from extraction.state where key = 'contacts_start'").fetchone()
    return datetime.fromisoformat(r["value"]["at"]) if r else None


def set_contacts_start(at: datetime | None = None) -> str:
    at = at or datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute("""insert into extraction.state (key, value) values ('contacts_start', %s)
                        on conflict (key) do update set value = excluded.value, updated_at = now()""",
                     (json.dumps({"at": at.isoformat()}),))
    return at.isoformat()


def contacts_on() -> bool:
    from . import organic
    return str((organic.settings().get("extraction") or {}).get("contacts", "single")) == "single"


def _thread_start(conn, source: str, thread_id: str) -> datetime | None:
    """Eligibility start of a thread for the live worker: its explicit catch-up start if one was requested, else the
    later of the V1 start and the live start (the backlog before it is backfill's)."""
    r = conn.execute("select from_at from extraction.threads where processor = %s and source = %s and thread_id = %s",
                     (PROCESSOR, source, thread_id)).fetchone()
    if r and r["from_at"]:
        return r["from_at"]
    starts = [x for x in (v1_start(conn), live_start(conn)) if x]
    if channel(source) == "contact":        # never before the contacts' own start: no sweep of their history
        cs = contacts_start(conn)
        return max(starts + [cs]) if cs and contacts_on() else datetime.max.replace(tzinfo=timezone.utc)
    return max(starts) if starts else None


def mark_dirty(conn, source: str, thread_id: str, last_event_at=None) -> None:
    conn.execute("""insert into extraction.threads (processor, source, thread_id, status, last_event_at, dirty_since)
                    values (%s, %s, %s, 'dirty', %s, now())
                    on conflict (processor, source, thread_id) do update set
                      last_event_at = greatest(extraction.threads.last_event_at, excluded.last_event_at),
                      status = case when extraction.threads.status = 'working' then 'working' else 'dirty' end,
                      dirty_since = coalesce(extraction.threads.dirty_since, now()), updated_at = now()""",
                 (PROCESSOR, source, thread_id, last_event_at))


def on_bus_events(evs: list[dict]) -> int:
    """Bus consumer handler (memory.event): a new message of a runtime, or of a 1:1 conversation with a contact, makes
    its thread dirty. Idempotent."""
    n = 0
    with connection() as conn:
        contact = [ev.get("subject") for ev in evs if (ev.get("payload") or {}).get("source") in CONTACT_SOURCES
                   and (ev.get("payload") or {}).get("event_type") in MESSAGE_TYPES]
        single = set()
        if contact and contacts_on() and contacts_start(conn):
            single = {r["id"] for r in conn.execute(
                """select event_id::text id from core.events where event_id = any(%s::uuid[])
                   and payload->'chat'->>'type' = 'single'""", ([c for c in contact if c],)).fetchall()}
        for ev in evs:
            p = ev.get("payload") or {}
            if p.get("event_type") not in MESSAGE_TYPES or not p.get("thread_id"):
                continue
            if p.get("source") in RUNTIMES or (p.get("source") in CONTACT_SOURCES and ev.get("subject") in single):
                mark_dirty(conn, p["source"], p["thread_id"], p.get("occurred_at"))
                n += 1
    return n


# ───────────────────────────── reading a thread ─────────────────────────────
def _noise(m: dict) -> str | None:
    from .views import INJECTED, NOISE, is_test_session
    text = RUNTIME_NOTES.sub("", INJECTED.sub("", m["content"] or "")).strip()
    if not text:
        return "empty"
    if m["event_type"] == "message.sent" and NOISE.match(text):
        return "injected"
    if AUTOMATED.match(text) or m.get("model") == "codex-auto-review":
        return "automated_review"
    if is_test_session(m["thread_id"] or "", m.get("cwd") or ""):
        return "test_session"
    return None


def pending_events(conn, source: str, thread_id: str, start: datetime | None) -> list[dict]:
    return conn.execute("""
        select e.event_id, e.event_type, e.occurred_at, e.ingested_at, e.content, e.privacy_class, e.thread_id,
               e.payload->>'model' as model, e.payload->>'cwd' as cwd, e.source, e.source_id, e.object_refs,
               e.actor_identity_id::text as actor, e.payload->'chat'->>'type' as chat_type,
               e.payload->'attachments' as files
        from core.events e
        where e.source = %s and e.thread_id = %s and e.event_type = any(%s)
          and (%s::timestamptz is null or e.ingested_at >= %s::timestamptz)
          and not exists (select 1 from extraction.covered c where c.processor = %s and c.event_id = e.event_id)
          and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                          and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
        order by e.occurred_at, e.event_id""",
                        (source, thread_id, list(MESSAGE_TYPES), start, start, PROCESSOR)).fetchall()


def contact_messages(conn, rows: list[dict], now: datetime | None = None) -> list[dict]:
    """A contact conversation as the extraction reads it (E2E 20/11): 1:1 chats only; each message says who spoke
    (speaker, speaker_id = the contact's entity through a CONFIRMED identity link, never a name match) and carries the
    words of its files (a voice note's transcript, a document's text), so quotes are checked against them. A file whose
    text is not derived yet and arrived less than AWAIT_TEXT ago sets `awaiting` (the reader holds from there)."""
    from . import events as ev_mod
    rows = [dict(r) for r in rows if r.get("chat_type") == "single"]
    if not rows:
        return []
    now = now or datetime.now(timezone.utc)
    actors = sorted({r["actor"] for r in rows if r.get("actor") and r["event_type"] == "message.received"})
    who = {r["identity_id"]: r for r in conn.execute(
        """select l.identity_id::text identity_id, l.entity_id::text entity_id, coalesce(en.canonical_name,
                  si.display_name) as name
           from core.identity_links l join core.entities en on en.entity_id = l.entity_id
           join core.source_identities si on si.identity_id = l.identity_id
           where l.identity_id = any(%s::uuid[]) and l.status = 'confirmed'""", (actors,)).fetchall()} if actors else {}
    readable = ev_mod.attachments(rows, max_privacy="redacted_cloud", chars=MSG_CHARS, conn=conn)
    open_ = ev_mod.attachments(rows, max_privacy="cloud_allowed", chars=MSG_CHARS, conn=conn)
    for r in rows:
        if r["event_type"] == "message.sent":
            r["speaker"], r["speaker_id"] = "Monsieur", None
        else:
            w = who.get(r.get("actor") or "") or {}
            r["speaker"], r["speaker_id"] = w.get("name") or "Contact", w.get("entity_id")
        files = readable.get(str(r["event_id"]), [])
        said = [ev_mod.attachment_line(a) for a in files if a.get("text")]
        if said:
            r["content"] = "\n".join(x for x in [r["content"] or ""] + said if x)
            if any(a.get("text") and not any(b["object_id"] == a["object_id"] and b.get("text") for b in
                                              open_.get(str(r["event_id"]), [])) for a in files):
                r["privacy_class"] = privacy.strictest(r["privacy_class"], "redacted_cloud")
        stored_waiting = any(a.get("text") is None and a.get("kind") in ("audio", "document") for a in files)
        queued = not files and any((f or {}).get("isVoiceNote") or str((f or {}).get("type")).lower() == "audio"
                                   for f in (r.get("files") or []))
        r["awaiting"] = (stored_waiting or queued) and now - r["ingested_at"] < AWAIT_TEXT
    return rows


def _context(conn, source: str, thread_id: str, before) -> list[dict]:
    rows = conn.execute("""select e.event_id, e.event_type, e.occurred_at, e.ingested_at, e.content,
                                  e.payload->>'model' as model, e.thread_id, e.privacy_class,
                                  e.payload->>'cwd' as cwd, e.source, e.source_id, e.object_refs,
                                  e.actor_identity_id::text as actor, e.payload->'chat'->>'type' as chat_type,
                                  e.payload->'attachments' as files from core.events e
                           where e.source = %s and e.thread_id = %s and e.event_type = any(%s)
                             and e.occurred_at < %s and e.privacy_class = 'cloud_allowed'
                           order by e.occurred_at desc limit 20""",
                        (source, thread_id, list(MESSAGE_TYPES), before)).fetchall()
    if channel(source) == "contact":
        rows = contact_messages(conn, rows)
    return [r for r in rows if not _noise(r)][:CONTEXT_MSGS][::-1]


def _known(conn, source: str, thread_id: str, text: str, generations: tuple = ("g1",)) -> list[dict]:
    """Current v2 knowledge the model may restate, supersede or contradict: this thread's latest items and the most
    similar ones anywhere (local embeddings, no model call). A staged backfill also sees its own staging generation."""
    gens = list(generations)
    rows = conn.execute("""select item_id::text, kind, content, coalesce(stage, attributes->>'state') as state,
                                  created_at, lineage_id::text, coalesce(valid_from, created_at) as at, generation,
                                  stage, epistemic, privacy_class, status, scope, attributes
                           from core.derived_items where derived_by = %s and status in ('derived','verified')
                             and (valid_to is null or valid_to > now())
                             and generation = any(%s) and kind <> 'summary'
                             and ((source_refs->>'thread' = %s and source_refs->>'source' = %s)
                                  or coalesce(attributes->'threads', '[]'::jsonb) ? %s)
                           order by created_at desc limit %s""",
                        (PROCESSOR, gens, thread_id, source, f"{source}/{thread_id}", KNOWN_THREAD)).fetchall()
    try:
        from . import search
        v = search.vec(search.embed([text[:4000]])[0])
        rows += conn.execute("""select d.item_id::text, d.kind, d.content, coalesce(d.stage, d.attributes->>'state') as state,
                                       d.created_at, d.lineage_id::text, coalesce(d.valid_from, d.created_at) as at,
                                       d.generation, d.stage, d.epistemic, d.privacy_class, d.status, d.scope, d.attributes
                                from search.chunks c join core.derived_items d on d.item_id = c.ref_id
                                where c.kind = 'derived' and c.embedding is not null and d.derived_by = %s
                                  and d.generation = any(%s) and d.status in ('derived','verified') and d.kind <> 'summary'
                                  and (d.valid_to is null or d.valid_to > now())
                                order by c.embedding <=> %s::vector limit %s""",
                             (PROCESSOR, gens, v, KNOWN_SIMILAR)).fetchall()
    except Exception as e:  # the embedder is an optimisation: the thread's own items are enough to go on
        log.warning("known items: similarity lookup failed: %s", e)
    seen, out = set(), []
    for r in rows:
        if r["item_id"] not in seen:
            seen.add(r["item_id"]); out.append(r)
    return out


# ───────────────────────────── segmentation ─────────────────────────────
def _size(m: dict) -> int:
    return min(len(m["content"] or ""), MSG_CHARS)


def due_segments(msgs: list[dict], now: datetime | None = None) -> tuple[list[list[dict]], list[dict]]:
    """Split pending messages into segments ready now and a tail that keeps waiting. Ready = full segments
    (SEGMENT_CHARS), and the rest once the conversation is quiet (no message for IDLE) or its oldest pending message
    has waited MAX_WAIT since ingestion."""
    now = now or datetime.now(timezone.utc)
    segs, cur, size = [], [], 0
    for m in msgs:
        if cur and size + _size(m) > SEGMENT_CHARS:
            segs.append(cur); cur, size = [], 0
        cur.append(m); size += _size(m)
    if cur:
        quiet = now - max(m["occurred_at"] for m in cur) >= IDLE           # the conversation has paused
        waited = now - min(m["ingested_at"] for m in cur) >= MAX_WAIT      # or its oldest message waited long enough
        if quiet or waited:
            segs.append(cur); cur = []
    return segs, cur


def adaptive_due(msgs: list[dict], now: datetime | None = None) -> tuple[list[list[dict]], list[dict], str | None]:
    """Adaptive policy (P1.1): segments ready now, the waiting tail, and why. The tail is interpreted at once when its
    turn is closed (the assistant answered) and an owner message in it is long or sets something (MARKERS); otherwise
    when ADAPT_TURNS owner turns accumulate, after ADAPT_QUIET of calm, or after MAX_WAIT. Full segments as before."""
    now = now or datetime.now(timezone.utc)
    segs, cur, size = [], [], 0
    for m in msgs:
        if cur and size + _size(m) > SEGMENT_CHARS:
            segs.append(cur); cur, size = [], 0
        cur.append(m); size += _size(m)
    if not cur:
        return segs, [], "full" if segs else None
    owners = [m for m in cur if m["event_type"] == "message.sent"]
    closed = cur[-1]["event_type"] == "message.received"
    clean = [RUNTIME_NOTES.sub("", m["content"] or "") for m in owners]
    reason = None
    if now - max(m["occurred_at"] for m in cur) >= ADAPT_QUIET:
        reason = "quiet"
    elif closed and any(len(t) >= LONG_MESSAGE for t in clean):
        reason = "long"
    elif closed and any(MARKERS.search(t) for t in clean):
        reason = "marker"
    elif closed and any(DIRECTIVE.search(t) for t in clean):
        reason = "directive"
    elif closed and len(owners) >= ADAPT_TURNS:
        reason = "turns"
    elif now - min(m["ingested_at"] for m in cur) >= MAX_WAIT:
        reason = "max_wait"
    if reason:
        return segs + [cur], [], reason
    return segs, cur, ("full" if segs else None)


def policy() -> str:
    """organic.toml [working_memory] mode: 'adaptive' = the adaptive trigger drives extraction; 'shadow' (default) =
    the 20-minute policy drives it and the adaptive decisions are only recorded; 'off' = neither."""
    from . import organic
    return organic.settings().get("working_memory", {}).get("mode", "shadow")


# ───────────────────────────── validation ─────────────────────────────
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def quote_found(quote: str, texts: list[str]) -> bool:
    q = _norm(quote)
    words = q.split()
    if len(words) < 3:
        return False
    for t in texts:
        n = _norm(t)
        if q in n:
            return True
        tokens = set(n.split())
        if sum(w in tokens for w in words) / len(words) >= 0.85:
            return True
    return False


def project_id(name) -> str | None:
    """A stable project identifier: lower case, ascii, words joined by '-'; « W.Alter … » → walter-…."""
    if not isinstance(name, str) or not name.strip() or name.strip().lower() in ("null", "none", "-"):
        return None
    n = _norm(name.split(":", 1)[-1]).replace(" ", "-")
    n = re.sub(r"^w-alter", "walter", n)
    return n[:60] or None


def validate(item: dict, seg: list[dict], known: dict[str, dict], *, chan: str = "agent") -> tuple[dict | None, str | None]:
    """→ (clean statement, None) or (None, reason). Pure: no database. Accepts the typed format (v3: type, author,
    domain, project, about) and the former one (kind, same_as, supersedes, contradicts: kept as the extraction's
    own hints, used as candidates, and as verdicts only in reconcile mode "model")."""
    typ = (item.get("type") or "").strip().lower().replace("é", "e").replace("è", "e")
    if typ in TYPES:
        kind, act = TYPES[typ]
        typed = True
    else:
        typed = False
        kind = (item.get("kind") or "").strip().lower()
        if kind not in KINDS:
            return None, "bad_kind"
        act = LEGACY_ACT[kind]
    text = (item.get("text") or "").strip()
    if len(text) < 8:
        return None, "empty_text"
    nums = item.get("msgs") or []
    if not isinstance(nums, list) or not nums or not all(isinstance(n, int) and 1 <= n <= len(seg) for n in nums):
        return None, "invalid_citation"
    cited = [seg[n - 1] for n in sorted(set(nums))]
    if not quote_found(item.get("quote") or "", [m["content"] or "" for m in cited]):
        return None, "quote_not_found"
    domain = DOMAINS.get((item.get("domain") or "").strip().lower())
    if domain == "test":
        return None, "test"                       # test data never becomes knowledge
    by_owner = any(m["event_type"] == "message.sent" for m in cited)
    by_agent = chan == "agent" and any(m["event_type"] == "message.received" for m in cited)
    # a contact conversation: received = the contact. Who states it is who wrote the cited messages, whatever the
    # model says; a statement of the contact is a third party's word (E2E 20/11)
    by_contact = chan == "contact" and any(m["event_type"] == "message.received" for m in cited)
    speaker_ids = sorted({m["speaker_id"] for m in cited if m.get("speaker_id")})
    if chan == "contact":
        a_ = (item.get("author") or "").strip().lower()
        if a_ in ("contact", "tiers") and by_contact:
            by_owner = False                      # the owner's message is only cited as context of his contact's word
        elif a_ == "monsieur" and by_owner:
            by_contact = False
        if by_contact and not by_owner and typ in ("decision",):
            typ, kind, act = "proposition", "decision", "proposal"   # a contact's « decision » about the owner: proposed
    raw_stage = (item.get("stage") or item.get("state") or "").strip().lower().replace("é", "e")
    if act == "decision" and raw_stage == "proposed":
        act = "proposal"
    if act == "decision" and raw_stage in ("abandoned", "abandonnee"):
        act = "cancel"
    if act == "action" and kind == "commitment" and raw_stage in ("", "stated"):
        raw_stage = "open"
    # stage of the stored item
    if act == "proposal":
        stage = "proposed"
    elif act == "cancel":
        stage = "abandoned"
    elif act in ACT_STAGES:     # an unknown stage ("verified" from a model) is never taken: the act's first stage
        stage = ACT_STAGES[act].get(raw_stage) or {"action": "open", "goal": "requested",
                                                    "decision": "decided" if typed and not raw_stage else "requested"}[act]
    elif act == "result":
        stage = "executed"                        # verified only with a proof (extract_segment reads it)
    else:
        stage = "stated"
    if (act in OWNER_ACTS or act == "decision") and not by_owner:
        return None, "no_owner_evidence"          # a goal, rule, decision or cancellation is the owner's word; the
                                                  # assistant's one is a proposition (typed so by the model)
    if stage in ("decided", "requested", "abandoned") and not by_owner:
        stage = "proposed"
    if stage == "executed" and act == "decision" and not by_agent:
        stage = "decided"                         # "it is done" needs a report of it; the owner's request is not one
    scope = (item.get("scope") or "durable").strip().lower()
    scope = scope if scope in SCOPES else "durable"
    until = None
    if item.get("until"):
        try:
            until = datetime.fromisoformat(str(item.get("until"))[:10]).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            until = None
    if scope == "until" and not until:
        scope = "task"
    author = (item.get("author") or "").strip().lower()
    if author in ("tiers", "third", "third_party") or (by_contact and not by_owner):
        epistemic_v = "stated_third_party"
    elif act == "hypothesis":
        epistemic_v = "inferred"
    else:
        epistemic_v = "stated_owner" if by_owner else "agent_reported"
    subject = (item.get("subject") or "").strip()[:120]
    about_entities: list[str] = []
    if chan == "contact":                         # whom the statement is about: the contact by its entity, not a name
        w_ = (item.get("who") or "").strip()
        contact = next((m for m in seg if m["event_type"] == "message.received" and m.get("speaker_id")), None)
        if w_.lower() in ("contact", "") and contact:
            subject, about_entities = f"person:{contact['speaker']}", [contact["speaker_id"]]
            domain = domain if domain in ("relation", "test") else "relation"
        elif w_.lower() in ("monsieur", "owner"):
            subject, domain = "owner", domain if domain in ("personal", "test") else "personal"
        elif w_:
            subject = f"person:{w_[:80]}"
            domain = domain if domain == "test" else "relation"
    project = project_id(item.get("project")) or (project_id(subject) if subject.lower().startswith("project:") else None)
    if domain is None:                            # former format: from the subject
        domain = ("project" if project else "personal" if subject.lower() in ("owner", "monsieur")
                  else "relation" if subject.lower().startswith("person:") else None)
    if domain in ("personal", "relation"):
        project = None
    refs = lambda key: [k for k in (item.get(key) or []) if isinstance(k, str) and k in known]   # noqa: E731
    same = item.get("same_as") if isinstance(item.get("same_as"), str) and item.get("same_as") in known else None
    supersedes, contradicts = refs("supersedes"), refs("contradicts")
    about = item.get("about") if isinstance(item.get("about"), str) and item.get("about") in known else None
    # only the owner's word replaces knowledge; otherwise flag the conflict — except a contact updating what HE said
    # before (« j'ai quitté Lyon ») : the same speaker's newer word replaces his older one (E2E 20/11)
    own_word = lambda k: by_contact and speaker_ids and (known[k].get("attributes") or {}).get("speaker_id") in speaker_ids  # noqa: E731
    if supersedes and not by_owner and not all(own_word(k) for k in supersedes):
        contradicts, supersedes = contradicts + supersedes, []
    hint = (("confirms", same) if same else ("replaces", supersedes[0]) if supersedes
            else ("contradicts", contradicts[0]) if contradicts else (None, about) if about else None)
    try:
        conf = max(0.0, min(1.0, float(item.get("confidence") or 0.7)))
    except (TypeError, ValueError):
        conf = 0.7
    return {"kind": kind, "act": act, "text": text, "state": stage, "stage": stage, "scope": scope, "until": until,
            # the 19/11 format gives no subject: a personal statement is the owner's (it was filed under « other »)
            "subject": subject or (f"project:{project}" if project else "owner" if domain == "personal" else "other"),
            "domain": domain, "project": project,
            "quote": (item.get("quote") or "")[:400], "cited": cited, "by_owner": by_owner, "by_agent": by_agent,
            "epistemic": "owner_stated" if by_owner else "third_party" if by_contact else "agent_reported",
            "epistemic_v": epistemic_v, "by_contact": by_contact, "speaker_ids": speaker_ids,
            "about_entities": about_entities,
            "same_as": same, "supersedes": supersedes, "contradicts": contradicts, "about": about, "hint": hint,
            "hint_id": known[hint[1]].get("item_id") if hint else None,
            "confidence": conf}, None


# ───────────────────────────── one segment ─────────────────────────────
def _segment_row(conn, *, source, thread_id, status, msgs, items=0, reused=0, superseded=0, rejected=None,
                 model=None, cost=None, usage=None, latency_ms=None, error=None) -> str:
    lag = None
    if msgs:
        newest = max(m["ingested_at"] for m in msgs)
        lag = int((datetime.now(timezone.utc) - newest).total_seconds())
    sid = conn.execute("""insert into extraction.segments (processor, version, source, thread_id, status, event_ids,
                              first_at, last_at, items, reused, superseded, rejected, model, prompt_hash, cost_usd,
                              usage, latency_ms, lag_s, error)
                          values (%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          returning segment_id::text""",
                       (PROCESSOR, VERSION, source, thread_id, status, [str(m["event_id"]) for m in msgs],
                        min((m["occurred_at"] for m in msgs), default=None),
                        max((m["occurred_at"] for m in msgs), default=None), items, reused, superseded,
                        json.dumps(rejected or [], ensure_ascii=False, default=str), model, PROMPT_HASH, cost,
                        json.dumps(usage or {}), latency_ms, lag, error)).fetchone()["segment_id"]
    if status != "failed" or error == "max_attempts":
        for m in msgs:
            conn.execute("""insert into extraction.covered (processor, event_id, segment_id) values (%s, %s, %s)
                            on conflict do nothing""", (PROCESSOR, m["event_id"], sid))
    return sid


def _line(i: int, m: dict, prefix: str = "") -> str:
    who = "Monsieur" if m["event_type"] == "message.sent" else m.get("speaker") or "W.Alter"
    from .views import INJECTED
    text = RUNTIME_NOTES.sub("", INJECTED.sub("", m["content"] or "")).strip()[:MSG_CHARS]
    return f"{prefix}{i}. [{who} · {m['occurred_at']:%Y-%m-%d %H:%M}] {text}"


def _projects(conn, gens: list[str]) -> list[str]:
    """Project identifiers already given to statements (lot 1): the model reuses them instead of inventing variants."""
    return [r["p"] for r in conn.execute("""select attributes->>'project' as p, count(*) n from core.derived_items
                                            where derived_by = %s and generation = any(%s) and attributes ? 'project'
                                              and status in ('derived','verified','superseded')
                                            group by 1 order by 2 desc limit 30""", (PROCESSOR, gens))]


def _pseudo(j: int, st: dict, cls: str, generation: str) -> dict:
    """An earlier statement of the same segment as a candidate (a goal asked, then reported done, in one segment)."""
    return {"item_id": f"seg:{j}", "kind": st["kind"], "content": st["text"], "stage": st["stage"], "scope": st["scope"],
            "epistemic": st["epistemic_v"], "status": "derived", "generation": generation, "lineage_id": None,
            "privacy_class": cls, "attributes": {}, "at": st["at"]}


def extract_segment(source: str, thread_id: str, seg: list[dict], *, chat=None, budget: str = "recurring",
                    backfill: str | None = None, generation: str = "g1") -> dict:
    """One extraction call for a segment of cloud-readable, non-noise messages, then the consolidation loop (lot 1,
    knowledge.py): each typed statement is reconciled with current knowledge (candidates from the hybrid search and
    the thread; verdicts deterministic or from Walter Decision, one batched decision per segment) and written through
    the single write gate, with the segment's coverage, atomically.
    backfill: the tag of a selective catch-up (backfill()): no segment summary, items carry attributes.backfill = tag,
    every change is recorded under that tag (knowledge.revert undoes it).
    generation: a staging generation (STAGING, never readable) writes a pilot apart from served knowledge: new items go
    there; changes it would make to served items are recorded `staged` in core.derived_changes, never applied."""
    from . import knowledge
    chat = chat or llm.chat
    chan = channel(source)
    staged = generation != "g1"
    gens = ["g1", generation] if staged else ["g1"]
    rc = knowledge.settings()
    with connection() as conn:
        context = _context(conn, source, thread_id, seg[0]["occurred_at"])
        known_rows = _known(conn, source, thread_id, "\n".join((m["content"] or "")[:500] for m in seg), tuple(gens))
        projects = _projects(conn, gens)
    known = {f"K{i + 1}": r for i, r in enumerate(known_rows)}
    seg_class = privacy.strictest(*(m["privacy_class"] for m in seg))
    fields = dict(
        context="\n".join(_line(i + 1, m, "C") for i, m in enumerate(context)) or "(début de conversation)",
        known="\n".join(f"{k}. [{r['kind']}{'/' + r['state'] if r['state'] and r['state'] != 'stated' else ''}] {r['content']}"
                        for k, r in known.items()) or "(aucune)",
        transcript="\n".join(_line(i + 1, m) for i, m in enumerate(seg)))
    if chan == "contact":
        name = next((m["speaker"] for m in seg + context if m["event_type"] == "message.received"
                     and m.get("speaker")), "le contact")
        prompt, prompt_hash = PROMPT_CONTACT.format(contact=name, **fields), PROMPT_CONTACT_HASH
    else:
        prompt, prompt_hash = PROMPT.format(projects=", ".join(projects) or "(aucun encore)", **fields), PROMPT_HASH
    t0 = time.perf_counter()
    res = chat([{"role": "user", "content": prompt}], poste=POSTE, processor=PROCESSOR, processor_version=VERSION,
               privacy_class=seg_class, budget=budget, purpose=f"{source} {thread_id} {len(seg)} msgs",
               response_format={"type": "json_object"}, max_tokens=6000, timeout=300)
    latency = int((time.perf_counter() - t0) * 1000)
    c = res["content"] or ""
    data = json.loads(c[c.find("{"):c.rfind("}") + 1])
    kept, rejected = [], []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        item, why = validate(raw, seg, known, chan=chan)
        if why:
            rejected.append({"reason": why, "item": {k: raw.get(k) for k in ("type", "kind", "text", "msgs", "quote")}})
        else:
            item["at"] = item["cited"][-1]["occurred_at"]
            item["cls"] = privacy.strictest(*(m["privacy_class"] for m in item["cited"]))
            kept.append(item)

    # ── reconciliation: candidates and verdicts (reads + one batched decision; no write transaction is held) ──
    verdicts: list[tuple] = []
    pending: list[tuple[str, dict, list[dict]]] = []
    cands_of: dict[int, list[dict]] = {}
    with connection() as conn:
        for j, st in enumerate(kept):
            pool = known_rows + [_pseudo(i, kept[i], kept[i]["cls"], generation) for i in range(j)]
            cands = knowledge.candidates(conn, st, pool, gens, rc["candidates"])
            hinted = known.get((st["hint"] or (None, None))[1]) if st["hint"] else None
            if hinted and hinted["item_id"] not in {x["item_id"] for x in cands}:
                cands.append(hinted)              # the extraction's own K reference joins the candidates
            cands_of[j] = cands
            if st["act"] == "result" or st["stage"] == "executed":    # what backs a report of work, read once
                st["proof"] = knowledge.proof(conn, source, thread_id, st["at"],
                                              owner=st["by_owner"] and st["act"] == "result")
            st["open_work"] = knowledge.open_work(pool) if st["act"] in knowledge.PROGRESS_ACTS else []
            det = knowledge.deterministic(st, cands)
            if det and det[0] == "new" and st["open_work"]:
                det = None                        # no same claim, but it may be the work of an open goal: ask
            hint = st["hint"] if st["hint"] and st["hint"][0] else None
            if rc["mode"] == "model" and hint:    # rollback switch: the extraction model's own references
                verdicts.append((hint[0], st["hint_id"], None, "model:extraction"))
            elif det:
                verdicts.append((det[0], det[1], None, f"deterministic:{det[2]}"))
            elif rc["mode"] in ("deterministic", "model"):
                verdicts.append(("new", None, None, "deterministic:no_rule"))
            else:
                verdicts.append(None)
                pending.append((f"s{j + 1}", st, cands))
    decisions = 0
    for part in knowledge.batches(pending, int(rc["batch"])):
        cls = privacy.strictest(seg_class, *(c["privacy_class"] for _, _, cs in part for c in cs))
        got = knowledge.judge(part, privacy_class=cls, budget=budget)
        decisions += 1
        for sid, _, _ in part:
            v, t, conf = got[sid]
            verdicts[int(sid[1:]) - 1] = (v, t, conf, f"decision:{knowledge.NEED}")

    # ── writes: one transaction, every change through the gate ──
    out = {"items": 0, "reused": 0, "superseded": 0, "advanced": 0, "contested": 0, "ignored": 0,
           "rejected": len(rejected), "decisions": decisions, "verdicts": {},
           "cost_usd": float(res.get("cost_usd") or 0)}
    with connection() as conn:
        status = "extracted" if kept or data.get("summary") else "empty"
        sid = _segment_row(conn, source=source, thread_id=thread_id, status=status, msgs=seg, rejected=rejected,
                           model=res.get("model"), cost=res.get("cost_usd"), usage=res.get("usage"), latency_ms=latency)
        base_refs = {"segment": sid, "thread": thread_id, "source": source}
        # the real subject, not the assistant's project by default (attribution.py, 19/11): deterministic, no model
        from . import attribution
        out["reattributed"] = attribution.for_segment(kept, conn)
        seg_projects = sorted({it["project"] for it in kept if it["project"]})
        if data.get("summary") and not backfill:
            conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                processor_version, model, prompt_hash, source_event_ids, source_refs, valid_from, privacy_class,
                                generation)
                            values ('summary', %s, %s, 'derived', %s, %s, %s, %s, %s::uuid[], %s, %s, %s, 'g1')""",
                         (data["summary"], json.dumps({"topics": data.get("topics") or [], "projects": seg_projects,
                                                       "people": data.get("people") or [], "from": str(seg[0]["occurred_at"]),
                                                       "to": str(seg[-1]["occurred_at"]), "pipeline": "v1"}, ensure_ascii=False),
                          PROCESSOR, VERSION, res.get("model"), prompt_hash, [str(m["event_id"]) for m in seg],
                          json.dumps({**base_refs, "ref": f"{sid}:summary"}), seg[-1]["occurred_at"], seg_class))
        gate = knowledge.Gate(conn, generation=generation, tag=backfill, segment=sid, where=f"{source}/{thread_id}")
        resolved: dict[str, str | None] = {}
        for j, it in enumerate(kept):
            verdict, target_id, conf, by = verdicts[j]
            if target_id and target_id.startswith("seg:"):
                target_id = resolved.get(target_id)
            target = _target(conn, target_id, gens) if target_id else None
            verdict, note = knowledge.guard(it, verdict, target, conf, rc["min_confidence"])
            ev_ids = [str(m["event_id"]) for m in it["cited"]]
            stage, epistemic, valid_to = it["stage"], it["epistemic_v"], it["until"]
            attrs = {"subject": it["subject"], "act": it["act"], "domain": it["domain"], "state": stage,
                     "epistemic": it["epistemic"], "quote": it["quote"], "pipeline": "v1"}
            if it["project"]:
                attrs["project"], attrs["projects"] = it["project"], [it["project"]]
            if it.get("attribution"):
                attrs["attribution"] = it["attribution"]
            pr = it.get("proof")
            if pr:
                attrs["proof"] = pr
                if it["act"] == "result" and knowledge.verifies(it, pr):
                    stage = "verified"
                    epistemic = "observed" if pr["level"] == "checked" else epistemic
            if backfill:
                attrs["backfill"] = backfill
            if it["kind"] == "commitment":
                attrs["holder"] = "owner" if it["by_owner"] else "contact" if it.get("by_contact") else "walter"
            if chan == "contact":          # who said it and whom it is about (entities, not names: E2E 20/11)
                attrs["channel"] = "contact"
                if it.get("speaker_ids"):
                    attrs["speaker_id"] = it["speaker_ids"][0]
                if it.get("about_entities"):
                    attrs["entities"] = it["about_entities"]
            if it["act"] == "state" and not valid_to:          # a transient state expires (task-scoped knowledge
                valid_to = it["at"] + timedelta(days=float(rc["state_ttl_days"]))   # expires with its work: consolidate.expire)
            row = {"kind": it["kind"], "content": it["text"], "attributes": attrs, "status": "derived",
                   "derived_by": PROCESSOR, "processor_version": VERSION, "model": res.get("model"),
                   "prompt_hash": prompt_hash, "source_event_ids": ev_ids,
                   "source_refs": {**base_refs, "ref": f"{sid}:{j}"}, "valid_from": it["at"],
                   "confidence": it["confidence"], "privacy_class": it["cls"], "generation": generation,
                   "epistemic": epistemic, "stage": stage, "scope": it["scope"], "valid_to": valid_to}
            r = knowledge.apply(gate, it, verdict, target, row=row, key=f"{sid}:{j}", decided_by=by,
                                confidence=conf, note=note,
                                proof_of=lambda st: st.get("proof") or knowledge.proof(conn, source, thread_id, st["at"],
                                                                                         owner=st["by_owner"]))
            resolved[f"seg:{j}"] = r.get("item") or target_id
            op = r.get("op")
            out["verdicts"][verdict] = out["verdicts"].get(verdict, 0) + 1
            out["items"] += op in ("created", "contested", "enriched", "corrected", "replaced", "older", "complemented")
            out["reused"] += op == "confirmed"
            out["superseded"] += op in ("enriched", "corrected", "replaced")
            out["advanced"] += op in ("advanced", "progress")
            out["contested"] += op == "contested"
            out["ignored"] += op == "ignored"
        out["runplane"] = len(knowledge.runplane(gate, source, thread_id)) if chan == "agent" else 0
        conn.execute("update extraction.segments set items = %s, reused = %s, superseded = %s where segment_id = %s",
                     (out["items"], out["reused"] + out["advanced"], out["superseded"], sid))
    out["segment_id"] = sid
    if staged:
        out["staged"] = gate.staged
    try:   # the index follows what changed (a later segment, another thread or the pilot finds it)
        from . import search
        search.reindex_derived(sorted(set(gate.changed)))
    except Exception as e:  # noqa: BLE001
        log.debug("reindex after extraction failed (index_pending catches up): %s", e)
    if staged:
        return out
    try:   # P1.2: the consolidated views built on this thread are rebuilt from the new state (targeted invalidation);
        # P1.6: a replaced or contested item also marks the episodes and periods that list it (and their parents)
        from . import consolidate
        consolidate.invalidate(threads=[(source, thread_id)], item_ids=sorted(set(gate.changed)) or None)
        from . import entities
        entities.link_items(conn_items_of_segment(sid))
    except Exception as e:
        log.warning("view invalidation / entity links failed (extraction kept): %s", e)
    return out


def _target(conn, item_id: str, gens: list[str]) -> dict | None:
    """The current version of a target: an item superseded meanwhile (by an earlier statement of the same segment)
    is followed to the version that replaced it."""
    for _ in range(6):
        r = conn.execute("""select item_id::text, kind, content, stage, scope, epistemic, status, generation,
                                   lineage_id::text, privacy_class, attributes, coalesce(valid_from, created_at) as at
                            from core.derived_items where item_id = %s and generation = any(%s)""",
                         (item_id, gens)).fetchone()
        if not r:
            return None
        if r["status"] in ("derived", "verified"):
            return r
        nxt = (r["attributes"] or {}).get("superseded_by")
        if r["status"] != "superseded" or not nxt:
            return None
        item_id = nxt
    return None


def conn_items_of_segment(sid) -> list[str]:
    with connection() as conn:
        return [r["item_id"] for r in conn.execute("""select item_id::text from core.derived_items
                                                      where derived_by = %s and source_refs->>'ref' like %s""",
                                                   (PROCESSOR, f"{sid}:%"))]


# ───────────────────────────── one thread ─────────────────────────────
def process_thread(source: str, thread_id: str, *, chat=None, budget: str = "recurring", now=None,
                   force: bool = False, mode: str | None = None) -> dict:
    """Handle what is due in one thread. force=True processes the waiting tail too (explicit runs, tests).
    mode: 'adaptive' or 'idle' (the 20-minute policy); default = the [working_memory] switch."""
    out = {"segments": 0, "items": 0, "reused": 0, "superseded": 0, "rejected": 0, "filtered": 0,
           "local_only": 0, "cost_usd": 0.0, "waiting": 0}
    with connection() as conn:
        start = _thread_start(conn, source, thread_id)
        msgs = pending_events(conn, source, thread_id, None if force else start)
        contact = channel(source) == "contact"
        if contact:      # 1:1 only, who spoke, the words of voice notes; a transcript still coming is waited for
            msgs = contact_messages(conn, msgs, now)
            held = next((i for i, m in enumerate(msgs) if m["awaiting"]), None)
            if held is not None:
                out["waiting"] += len(msgs) - held
                msgs = msgs[:held]
    if not msgs:
        return out
    # 1. never to a cloud model, never retried by this version
    closed = [m for m in msgs if not privacy.cloud_readable(m["privacy_class"])]
    if closed:
        with connection() as conn:
            _segment_row(conn, source=source, thread_id=thread_id, status="local_only_unavailable", msgs=closed,
                         error="no authorised local model: kept in history, not interpreted")
        out["local_only"] += len(closed)
    cloud = [m for m in msgs if privacy.cloud_readable(m["privacy_class"])]
    # 2. noise: covered without a model call
    noise = [m for m in cloud if _noise(m)]
    if noise:
        with connection() as conn:
            _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=noise,
                         rejected=[{"event_id": str(m["event_id"]), "reason": _noise(m)} for m in noise[:50]])
        out["filtered"] += len(noise)
    usable = [m for m in cloud if not _noise(m)]
    if contact:     # a human exchange is read whole: grouped until IDLE of calm (at most MAX_WAIT), so a question and
        segs, tail = due_segments(usable, now)          # its answer reach the model together (20/11 Beeper lot: 7 days
                                                        # of 1:1 traffic = 311 calls instead of 441 at 5 min of calm).
                                                        # No message is skipped as trivial: a lone « oui » or 👍 may
                                                        # accept a proposal made earlier.
    elif (mode or policy()) == "adaptive":
        segs, tail, out["reason"] = adaptive_due(usable, now)
    else:
        segs, tail = due_segments(usable, now)
    if force and tail:
        segs, tail = segs + [tail], []
    out["waiting"] = len(tail)
    from . import quota
    for i, seg in enumerate(segs):
        q = quota.gate()
        if not q["ok"]:                  # a real provider limit holds the poste: the rest of the thread waits
            out["quota_stopped"] = q["reason"]
            out["waiting"] += sum(len(x) for x in segs[i:])
            break
        if not contact and not any(m["event_type"] == "message.sent" for m in seg) and sum(_size(m) for m in seg) < 1500:
            with connection() as conn:   # assistant-only chatter: nothing the owner said, nothing substantial
                _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=seg,
                             rejected=[{"reason": "no_owner_message"}])
            out["filtered"] += len(seg)
            continue
        try:
            r = extract_segment(source, thread_id, seg, chat=chat, budget=budget)
        except quota.Waiting as w:       # met a real limit now: this and the next segments wait, nothing covered
            out["quota_stopped"] = str(w)
            out["waiting"] += sum(len(x) for x in segs[i:])
            break
        out["segments"] += 1
        for k in ("items", "reused", "superseded", "rejected"):
            out[k] += r[k]
        out["cost_usd"] += r["cost_usd"]
    return out


# ───────────────────────────── the worker ─────────────────────────────
HUMAN_SOURCES = ["beeper", "gmail"]   # conversations with people: read before the agents' sessions


def claim(limit: int = 8) -> list[dict]:
    """Lease due dirty threads (short transaction: no lock is held during model calls). The owner's conversations with
    people come first, then the oldest: an agent session is long to read (~40 s a segment) and must not keep a
    contact's proposal waiting behind it (20/11). Human traffic is small (~500 exchanges a week), so agents never
    starve."""
    with connection() as conn:
        return conn.execute("""
            update extraction.threads t set status = 'working', claimed_at = now(), updated_at = now()
            where (t.processor, t.source, t.thread_id) in (
                select processor, source, thread_id from extraction.threads
                where processor = %s and (status = 'dirty' or (status = 'working' and claimed_at < now() - %s))
                  and (retry_after is null or retry_after <= now())
                order by source <> all(%s), last_event_at nulls first limit %s for update skip locked)
            returning t.source, t.thread_id, t.attempts""", (PROCESSOR, LEASE, HUMAN_SOURCES, limit)).fetchall()


def _release(source: str, thread_id: str, *, error: str | None = None, attempts: int = 0, waiting: bool = False) -> None:
    with connection() as conn:
        if error:
            n = attempts + 1
            conn.execute("""update extraction.threads set status = 'dirty', attempts = %s, last_error = %s,
                              retry_after = now() + make_interval(secs => %s), claimed_at = null, updated_at = now()
                            where processor = %s and source = %s and thread_id = %s""",
                         (n, error[:1000], min(60 * 2 ** n, 6 * 3600), PROCESSOR, source, thread_id))
        else:
            conn.execute("""update extraction.threads set status = case when %s then 'dirty' else 'idle' end,
                              attempts = 0, last_error = null, retry_after = null, claimed_at = null,
                              dirty_since = case when %s then dirty_since else null end, updated_at = now()
                            where processor = %s and source = %s and thread_id = %s""",
                         (waiting, waiting, PROCESSOR, source, thread_id))


def _give_up(source: str, thread_id: str, error: str) -> None:
    """After MAX_ATTEMPTS the pending events are covered by a 'failed' segment (dead letter, `extract replay`)."""
    with connection() as conn:
        msgs = pending_events(conn, source, thread_id, _thread_start(conn, source, thread_id))
        if msgs:
            _segment_row(conn, source=source, thread_id=thread_id, status="failed", msgs=msgs, error="max_attempts",
                         rejected=[{"reason": error[:500]}])


def note_gate(state: str, q: dict | None = None) -> None:
    """The live extraction's last gate verdict, extraction.state 'live_gate' = {state: open | paused | provider_limit,
    since, at, reason, until}: what the situation projection shows as the delay of personal
    knowledge. `since` = when this state began (kept while it lasts). Written once a tick, never raises."""
    now = datetime.now(timezone.utc).isoformat()
    v = {"state": state, "at": now, "since": now,
         **{k: (q or {}).get(k) for k in ("reason", "until")}}
    try:
        with connection() as conn:
            conn.execute("""insert into extraction.state (key, value, updated_at) values ('live_gate', %s::jsonb, now())
                            on conflict (key) do update set updated_at = now(), value = excluded.value
                              || jsonb_build_object('since', case when extraction.state.value->>'state'
                                                                       = excluded.value->>'state'
                                                                  then coalesce(extraction.state.value->>'since',
                                                                                excluded.value->>'since')
                                                                  else excluded.value->>'since' end)""",
                         (json.dumps(v),))
    except Exception:  # noqa: BLE001 — an indicator, never a reason to stop the tick
        log.warning("extract2: live_gate not recorded", exc_info=True)


def live_status(conn) -> dict:
    """What the delay display reads (two indexed reads, a few ms): the gate's last verdict and the conversations
    waiting for extraction (dirty threads, the oldest first)."""
    g = conn.execute("select value, updated_at from extraction.state where key = 'live_gate'").fetchone()
    w = conn.execute("""select count(*) n, min(dirty_since) oldest from extraction.threads
                        where processor = %s and status = 'dirty'""", (PROCESSOR,)).fetchone()
    return {"gate": dict(g["value"], seen=g["updated_at"]) if g else None,
            "waiting": {"threads": w["n"], "oldest": w["oldest"]}}


def tick(limit: int = 8, workers: int = 4, chat=None, budget: str = "recurring") -> dict:
    import concurrent.futures as cf
    total = {"threads": 0, "segments": 0, "items": 0, "reused": 0, "superseded": 0, "rejected": 0, "filtered": 0,
             "local_only": 0, "cost_usd": 0.0, "errors": 0}
    from . import organic
    if organic.extraction_paused():      # nothing claimed: dirty threads stay pending until the pause ends
        note_gate("paused")
        return {**total, "paused": True}
    from . import quota
    q = quota.gate()
    if not q["ok"]:                      # a real provider limit holds the poste: nothing claimed until it lifts
        note_gate("provider_limit", q)
        return {**total, "quota": q}
    note_gate("open", q)
    claimed = claim(limit)

    def one(t):
        try:
            r = process_thread(t["source"], t["thread_id"], chat=chat, budget=budget)
            _release(t["source"], t["thread_id"], waiting=r["waiting"] > 0)
            return r
        except quota.Waiting as e:       # a real provider limit: the thread stays dirty, attempts unchanged
            _release(t["source"], t["thread_id"], waiting=True)
            return {"budget": str(e)}
        except llm.BudgetExceeded as e:
            _release(t["source"], t["thread_id"], waiting=True)
            return {"budget": str(e)}
        except Exception as e:
            log.exception("extract2: %s %s failed", t["source"], t["thread_id"])
            if t["attempts"] + 1 >= MAX_ATTEMPTS:
                _give_up(t["source"], t["thread_id"], f"{type(e).__name__}: {e}")
                _release(t["source"], t["thread_id"])
            else:
                _release(t["source"], t["thread_id"], error=f"{type(e).__name__}: {e}", attempts=t["attempts"])
            return None
    with cf.ThreadPoolExecutor(max(1, workers)) as ex:
        for r in ex.map(one, claimed):
            total["threads"] += 1
            if r is None:
                total["errors"] += 1
            elif "budget" in r:
                total["stopped"] = r["budget"]
            else:
                for k in total:
                    if k in r and k not in ("threads", "errors"):
                        total[k] += r[k]
    return total


def reconcile(window: timedelta = timedelta(days=3)) -> dict:
    """Mark dirty every thread with eligible uncovered events (bus loss, events from before the trigger, failed
    leases). Eligible = ingested after the V1 start and inside the window. Recorded in ingestion.reconciliation_runs."""
    with connection() as conn:
        start = v1_start(conn)
        if start is None:
            return {"skipped": "v1_start not set"}
        since = max(start, datetime.now(timezone.utc) - window)
        run_id = conn.execute("""insert into ingestion.reconciliation_runs (connector, stream) values ('extraction', %s)
                                 returning run_id""", (PROCESSOR,)).fetchone()["run_id"]
        rows = conn.execute("""
            select e.source, e.thread_id, max(e.occurred_at) as last_at, count(*) as n
            from core.events e
            where e.source = any(%s) and e.event_type = any(%s) and e.ingested_at >= %s and e.thread_id is not null
              and not exists (select 1 from extraction.covered c where c.processor = %s and c.event_id = e.event_id)
            group by 1, 2""", (list(RUNTIMES), list(MESSAGE_TYPES), since, PROCESSOR)).fetchall()
        cs = contacts_start(conn) if contacts_on() else None
        if cs:   # the owner's 1:1 conversations with his contacts, from their own start (E2E 20/11)
            rows += conn.execute("""
                select e.source, e.thread_id, max(e.occurred_at) as last_at, count(*) as n from core.events e
                where e.source = any(%s) and e.event_type = any(%s) and e.ingested_at >= greatest(%s, %s)
                  and e.thread_id is not null and e.payload->'chat'->>'type' = 'single'
                  and not exists (select 1 from extraction.covered c where c.processor = %s and c.event_id = e.event_id)
                group by 1, 2""", (list(CONTACT_SOURCES), list(MESSAGE_TYPES), since, cs, PROCESSOR)).fetchall()
        known = {(r["source"], r["thread_id"]) for r in conn.execute(
            "select source, thread_id from extraction.threads where processor = %s and status in ('dirty','working')",
            (PROCESSOR,)).fetchall()}
        total = conn.execute("""select count(*) n from core.events where source = any(%s) and event_type = any(%s)
                                and ingested_at >= %s""", (list(RUNTIMES), list(MESSAGE_TYPES), since)).fetchone()["n"]
        gaps = [r for r in rows if (r["source"], r["thread_id"]) not in known]
        for r in gaps:
            mark_dirty(conn, r["source"], r["thread_id"], r["last_at"])
        uncovered = sum(r["n"] for r in rows)
        conn.execute("""update ingestion.reconciliation_runs set finished_at = now(), source_count = %s,
                          walter_count = %s, gaps = %s, repaired = %s, details = %s where run_id = %s""",
                     (total, total - uncovered, len(gaps), len(gaps),
                      json.dumps({"since": since.isoformat(), "uncovered_events": uncovered,
                                  "threads_marked": [f"{r['source']}:{r['thread_id']}" for r in gaps[:50]]}), run_id))
    return {"since": since.isoformat(), "eligible": total, "uncovered": uncovered, "threads_marked": len(gaps)}


def enqueue(*, since: str | None = None, thread: str | None = None, source: str | None = None) -> int:
    """Targeted catch-up, on explicit request only (pre-V1 history is never swept automatically)."""
    with connection() as conn:
        rows = conn.execute("""select source, thread_id, max(occurred_at) last_at from core.events
                               where source = any(%s) and event_type = any(%s) and thread_id is not null
                                 and (%s::text is null or thread_id = %s) and (%s::text is null or source = %s)
                                 and (%s::timestamptz is null or occurred_at >= %s::timestamptz)
                               group by 1, 2""",
                            (list(RUNTIMES), list(MESSAGE_TYPES), thread, thread, source, source, since, since)).fetchall()
        for r in rows:
            mark_dirty(conn, r["source"], r["thread_id"], r["last_at"])
            conn.execute("""update extraction.threads set from_at = least(coalesce(from_at, 'infinity'), %s::timestamptz)
                            where processor = %s and source = %s and thread_id = %s""",
                         (since or "1970-01-01T00:00:00+00:00", PROCESSOR, r["source"], r["thread_id"]))
    return len(rows)


STAGING = "g1p"      # the pilot's generation (core.generations, never readable until the owner promotes it)


def _ensure_staging(generation: str) -> None:
    with connection() as conn:
        conn.execute("""insert into core.generations (generation, status, readable, description, note)
                        values (%s, 'candidate', false, 'staged V1 extraction (tagged backfill pilot): not read by '
                                || 'Context until promoted', 'pilot') on conflict (generation) do nothing""",
                     (generation,))


def _ledger(tag: str, generation: str, seg_ids: list[str], staged: list[dict] | None = None) -> None:
    """The backfill ledger (extraction.state 'backfill:<tag>'), written after every segment: a run interrupted at any
    point stays exactly revertible (backfill_revert reads it)."""
    with connection() as conn:
        conn.execute("""insert into extraction.state (key, value) values (%s, %s)
                        on conflict (key) do update set value = jsonb_set(extraction.state.value,
                          '{segments}', (select coalesce(jsonb_agg(distinct x), '[]'::jsonb) from
                            jsonb_array_elements_text(coalesce(extraction.state.value->'segments', '[]'::jsonb)
                                                      || (excluded.value->'segments')) x)),
                          updated_at = now()""",
                     (f"backfill:{tag}", json.dumps({"tag": tag, "segments": seg_ids, "generation": generation})))
        if staged:
            conn.execute("""update extraction.state set value = jsonb_set(value, '{staged}',
                              coalesce(value->'staged', '[]'::jsonb) || %s::jsonb) where key = %s""",
                         (json.dumps(staged, default=str), f"backfill:{tag}"))


def backfill(event_ids: list[str], *, tag: str, chat=None, budget: str = "backfill", window: int = 1,
             max_threads: int | None = None, workers: int = 4, dry: bool = False, generation: str = "g1") -> dict:
    """Selective catch-up of pre-V1 history (g0 → g1 migration, 2026-11-10): only the given messages, each with
    `window` neighbours on either side in its thread (the assistant turn an approval answers), go through the same
    extraction as live messages (same prompt, validation, supersession, privacy, entity links, view invalidation).
    Idempotent: covered events are never redone (extraction.covered). Reversible: every segment is listed under
    extraction.state['backfill:<tag>'] and backfill_revert(tag) retracts what it produced. Pre-V1 messages are never
    swept: only an explicit call reaches them.
    generation=STAGING: a pilot (2026-11-19) — items written apart (unreadable generation), effects on served knowledge
    recorded under the ledger's `staged`, never applied; backfill_revert(tag) then leaves served knowledge untouched.
    A real provider limit (quota.gate, held after every route refused) stops the run before or at a segment
    (quota_stopped); the next run resumes where it stopped."""
    from collections import defaultdict
    if generation != "g1" and not dry:
        _ensure_staging(generation)
    with connection() as conn:
        seeds = conn.execute("""select source, thread_id, occurred_at, event_id from core.events
                                where event_id = any(%s::uuid[]) and source = any(%s) and event_type = any(%s)
                                  and thread_id is not null""",
                             ([str(e) for e in event_ids], list(RUNTIMES), list(MESSAGE_TYPES))).fetchall()
    by_thread = defaultdict(set)
    for r in seeds:
        by_thread[(r["source"], r["thread_id"])].add(str(r["event_id"]))
    threads = sorted(by_thread)[:max_threads] if max_threads else sorted(by_thread)
    out = {"tag": tag, "seed_events": len(seeds), "threads": len(threads), "segments": 0, "items": 0, "reused": 0,
           "superseded": 0, "advanced": 0, "contested": 0, "ignored": 0, "decisions": 0, "rejected": 0, "filtered": 0,
           "skipped_covered": 0, "events": 0, "cost_usd": 0.0, "errors": 0, "busy": 0, "verdicts": {}}

    def one(key):
        source, thread_id = key
        res = {k: 0 for k in ("segments", "items", "reused", "superseded", "advanced", "contested", "ignored",
                              "decisions", "rejected", "filtered", "events", "skipped_covered", "errors", "busy")}
        res["cost_usd"], res["segment_ids"], res["staged"], res["verdicts"] = 0.0, [], [], {}
        if dry:
            return _one(key, res)
        # the live worker's lease (extraction.threads): a thread is never read by two extractions at once (live
        # worker, another backfill run). A busy thread is skipped: a later run takes it (its events stay uncovered).
        with connection() as conn:
            got = conn.execute("""insert into extraction.threads (processor, source, thread_id, status, claimed_at)
                                  values (%s, %s, %s, 'working', now())
                                  on conflict (processor, source, thread_id) do update
                                    set status = 'working', claimed_at = now(), updated_at = now()
                                  where extraction.threads.status <> 'working' or extraction.threads.claimed_at < now() - %s
                                  returning 1""", (PROCESSOR, source, thread_id, LEASE)).fetchone()
        if not got:
            res["busy"] = 1
            return res
        try:
            return _one(key, res)
        finally:
            with connection() as conn:   # back to what the live path expects: dirty if it marked new work meanwhile
                conn.execute("""update extraction.threads set claimed_at = null, updated_at = now(),
                                  status = case when dirty_since is not null then 'dirty' else 'idle' end
                                where processor = %s and source = %s and thread_id = %s""",
                             (PROCESSOR, source, thread_id))

    def _one(key, res):
        source, thread_id = key
        with connection() as conn:
            msgs = pending_events(conn, source, thread_id, None)        # uncovered messages of the thread
            allm = conn.execute("""select event_id::text from core.events where source = %s and thread_id = %s
                                   and event_type = any(%s) order by occurred_at, event_id""",
                                (source, thread_id, list(MESSAGE_TYPES))).fetchall()
        order = [r["event_id"] for r in allm]
        want = set()
        for e in by_thread[key]:
            if e in order:
                i = order.index(e)
                want |= set(order[max(0, i - window):i + window + 1])
        sel = [m for m in msgs if str(m["event_id"]) in want]
        res["skipped_covered"] = len(want) - len(sel)
        res["events"] = len(sel)
        if dry or not sel:
            return res
        usable = [m for m in sel if privacy.cloud_readable(m["privacy_class"]) and not _noise(m)]
        noise = [m for m in sel if privacy.cloud_readable(m["privacy_class"]) and _noise(m)]
        if noise:
            with connection() as conn:
                sid = _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=noise,
                                   rejected=[{"event_id": str(m["event_id"]), "reason": _noise(m)} for m in noise[:50]])
            res["filtered"] += len(noise)
            res["segment_ids"].append(str(sid))
            _ledger(tag, generation, [str(sid)])
        segs, cur, size = [], [], 0
        for m in usable:
            if cur and size + _size(m) > SEGMENT_CHARS:
                segs.append(cur); cur, size = [], 0
            cur.append(m); size += _size(m)
        if cur:
            segs.append(cur)
        from . import quota
        for seg in segs:
            q = quota.gate()
            if not q["ok"]:              # a real provider limit: the rest of the thread stays uncovered, a later run
                res["quota_stopped"] = q["reason"]      # takes it up
                break
            if not any(m["event_type"] == "message.sent" for m in seg):
                with connection() as conn:
                    sid = _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=seg,
                                       rejected=[{"reason": "no_owner_message"}])
                res["filtered"] += len(seg)
                res["segment_ids"].append(str(sid))
                _ledger(tag, generation, [str(sid)])
                continue
            with connection() as conn:   # keep the lease while this thread's segments go through
                conn.execute("""update extraction.threads set claimed_at = now() where processor = %s and source = %s
                                and thread_id = %s and status = 'working'""", (PROCESSOR, source, thread_id))
            try:
                r = extract_segment(source, thread_id, seg, chat=chat, budget=budget, backfill=tag,
                                    generation=generation)
            except quota.Waiting as w:   # a real provider limit met now: stop here, nothing covered
                res["quota_stopped"] = str(w)
                break
            except Exception as e:  # noqa: BLE001 — this thread is retried by a later run (nothing covered)
                log.warning("backfill %s %s: %s", source, thread_id, e)
                res["errors"] += 1
                continue
            res["segments"] += 1
            res["segment_ids"].append(str(r["segment_id"]))
            res["staged"] += r.get("staged") or []
            _ledger(tag, generation, [str(r["segment_id"])], r.get("staged"))
            for k in ("items", "reused", "superseded", "advanced", "contested", "ignored", "decisions", "rejected"):
                res[k] += r.get(k, 0)
            for v, n in (r.get("verdicts") or {}).items():
                res["verdicts"][v] = res["verdicts"].get(v, 0) + n
            res["cost_usd"] += r["cost_usd"]
        return res

    from concurrent.futures import ThreadPoolExecutor
    seg_ids: list[str] = []
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for res in ex.map(one, threads):
            seg_ids += res.pop("segment_ids")
            staged = res.pop("staged", [])
            out["staged"] = out.get("staged", 0) + len(staged)
            if res.get("quota_stopped"):
                out["quota_stopped"] = res.pop("quota_stopped")
            for v, n in res.pop("verdicts").items():
                out["verdicts"][v] = out["verdicts"].get(v, 0) + n
            for k, v in res.items():
                out[k] += v
    out["cost_usd"] = round(out["cost_usd"], 4)
    return out


def catchup(events: int = 120, *, workers: int = 2, dry: bool = False, chat=None, relate: int = 120) -> dict:
    """One run of the catch-up loop: a slice of the message history (catchup_messages), then a slice of the
    reconciliation of existing knowledge (knowledge.reconcile_existing, stage reconcile_existing: no Codex, so it goes
    on when the quota stops the messages)."""
    from . import knowledge, organic
    out = catchup_messages(events, workers=workers, dry=dry, chat=chat)
    if relate and not dry and organic.stage("reconcile_existing")["mode"] == "active":
        try:
            out["reconciled"] = knowledge.reconcile_existing(relate)
        except Exception as e:  # noqa: BLE001 — the next run takes it up
            log.warning("reconcile_existing failed: %s", e)
            out["reconciled"] = {"error": f"{type(e).__name__}: {e}"[:300]}
    return out


def catchup_messages(events: int = 120, *, workers: int = 2, dry: bool = False, chat=None) -> dict:
    """Production catch-up of the history (2026-11-19, owner: « lance le rattrapage de l'historique par tranches,
    sans dépasser le quota et sans laisser des événements anciens écraser des états plus récents »): the uncovered
    messages ingested between v1_start and live_start, OLDEST FIRST, one slice of `events` messages per call, through
    backfill() (same extraction, reconciliation and write gate as live; window=0 = only these messages).
    Order: slices follow occurred_at, and the write gate records a statement older than the knowledge it meets as
    past (op "older"), never as a replacement. Provider limit: asked before the slice and before every
    segment (a real refusal only, no percentage); held, nothing more is read and the next call resumes where this one
    stopped. Switch: organic.toml [stages] catchup.
    Ledger per day: tag rattrapage-YYYY-MM-DD (backfill_revert(tag) undoes one day of catch-up)."""
    from . import organic, quota
    if organic.stage("catchup")["mode"] != "active":
        return {"stopped": "paused"}
    q = quota.gate()
    if not q["ok"]:
        return {"stopped": "quota", "reason": q.get("reason"), "until": q.get("until")}
    sql = """from core.events e where e.source = any(%s) and e.event_type = any(%s) and e.thread_id is not null
               and e.ingested_at >= %s and e.ingested_at < %s
               and not exists (select 1 from extraction.covered cv where cv.processor = %s and cv.event_id = e.event_id)
               and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                               and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))"""
    with connection() as conn:
        v1, ls = v1_start(conn), live_start(conn)
        if v1 is None or ls is None:
            return {"stopped": "no_window"}
        args = (list(RUNTIMES), list(MESSAGE_TYPES), v1, ls, PROCESSOR)
        ids = [str(r["event_id"]) for r in conn.execute(
            f"select e.event_id {sql} order by e.occurred_at, e.event_id limit %s", (*args, events)).fetchall()]
        if not ids:
            return {"done": True, "remaining": 0}
    tag = f"rattrapage-{datetime.now(timezone.utc):%Y-%m-%d}"
    out = backfill(ids, tag=tag, chat=chat, window=0, workers=workers, dry=dry, generation="g1")
    with connection() as conn:
        out["remaining"] = conn.execute(f"select count(*) n {sql}", args).fetchone()["n"]
    return out


def backfill_revert(tag: str, *, confirm: bool = False) -> dict:
    """Undo backfill(tag): every change the write gate recorded under the tag is undone (knowledge.revert: items it
    created retracted, items it changed — evidence, supersession, contest, lifecycle — restored); items written before
    the gate (pilots up to 2026-11-19b) are retracted and what they had superseded is current again; its events are
    uncovered (a later backfill may redo them). Dry run unless confirm."""
    from . import knowledge
    gate = knowledge.revert(tag, confirm=confirm)
    with connection() as conn:
        st = conn.execute("select value from extraction.state where key = %s", (f"backfill:{tag}",)).fetchone()
        segs = (st["value"].get("segments") if st else None) or []
        items = [r["item_id"] for r in conn.execute(
            """select item_id::text from core.derived_items where derived_by = %s and attributes->>'backfill' = %s
               and status <> 'retracted'""", (PROCESSOR, tag))]
        revived = [r["item_id"] for r in conn.execute(
            """select item_id::text from core.derived_items where status = 'superseded'
               and attributes->>'superseded_by' = any(%s)
               and coalesce(attributes->>'backfill', '') <> %s""", (items, tag))]   # never one of its own
        contested = [r["source_id"] for r in conn.execute(
            """select distinct p.source_id::text from core.provenance p where p.target_table = 'derived_items'
               and p.role = 'contradicts' and p.target_id::text = any(%s)
               and not exists (select 1 from core.provenance q where q.target_table = 'derived_items'
                               and q.role = 'contradicts' and q.source_id = p.source_id
                               and not (q.target_id::text = any(%s)))""", (items, items))]
        # dry run: the items query still sees the gate's own items; once undone, they are counted by the gate
        out = {"tag": tag, "segments": len(segs), "items": len(items) + (gate["created"] if confirm else 0),
               "revived": len(revived), "uncontested": len(contested), "executed": confirm, "gate": gate}
        if not confirm:
            return out
        conn.execute("""update core.derived_items set status = 'retracted', valid_to = coalesce(valid_to, now()),
                          attributes = attributes || jsonb_build_object('retracted_by', 'backfill_revert')
                        where item_id = any(%s::uuid[])""", (items,))
        conn.execute("""update core.derived_items set status = 'derived', valid_to = null,
                          attributes = attributes - 'superseded_by' - 'replayed_older'
                        where item_id = any(%s::uuid[])""", (revived,))
        conn.execute("""update core.derived_items set attributes = attributes - 'contested'
                        where item_id = any(%s::uuid[])""", (contested,))
        conn.execute("""update search.chunks set hidden = true, hidden_reason = 'backfill_revert'
                        where kind = 'derived' and ref_id::text = any(%s)""", (items,))
        conn.execute("delete from extraction.covered where processor = %s and segment_id::text = any(%s)",
                     (PROCESSOR, segs))
        conn.execute("""update extraction.state set value = value || jsonb_build_object('reverted_at', now()::text)
                        where key = %s""", (f"backfill:{tag}",))
    try:
        from . import search
        search.reindex_derived(revived)
    except Exception as e:  # noqa: BLE001
        log.warning("reindex after revert failed: %s", e)
    return out


def replay(*, status: str = "failed", thread: str | None = None) -> int:
    """Un-cover the events of failed (or local_only_unavailable, once a local model exists) segments: they are
    processed again by the worker."""
    with connection() as conn:
        segs = conn.execute("""select segment_id, source, thread_id from extraction.segments
                               where processor = %s and status = %s and (%s::text is null or thread_id = %s)""",
                            (PROCESSOR, status, thread, thread)).fetchall()
        for s in segs:
            conn.execute("delete from extraction.covered where processor = %s and segment_id = %s",
                         (PROCESSOR, s["segment_id"]))
            mark_dirty(conn, s["source"], s["thread_id"])
    return len(segs)


def stats(hours: int = 24) -> dict:
    """Freshness and volume: what waits, how late knowledge is written after the event, costs and rejections."""
    with connection() as conn:
        start = v1_start(conn)
        q = conn.execute("""select status, count(*) n, min(dirty_since) oldest from extraction.threads
                            where processor = %s group by 1""", (PROCESSOR,)).fetchall()
        s = conn.execute("""select status, count(*) segments, sum(array_length(event_ids, 1)) events, sum(items) items,
                                   sum(reused) reused, sum(superseded) superseded,
                                   sum(jsonb_array_length(rejected)) filter (where status = 'extracted') rejected,
                                   round(sum(cost_usd)::numeric, 4) cost_usd,
                                   percentile_cont(0.5) within group (order by lag_s) lag_p50_s,
                                   percentile_cont(0.95) within group (order by lag_s) lag_p95_s,
                                   percentile_cont(0.5) within group (order by latency_ms) model_ms_p50
                            from extraction.segments where processor = %s and created_at > now() - make_interval(hours => %s)
                            group by 1""", (PROCESSOR, hours)).fetchall()
        backlog = conn.execute("""select count(*) n, extract(epoch from now() - min(e.ingested_at))::int oldest_s
                                  from core.events e where e.source = any(%s) and e.event_type = any(%s)
                                    and e.ingested_at >= coalesce(%s, now())
                                    and not exists (select 1 from extraction.covered c where c.processor = %s
                                                    and c.event_id = e.event_id)""",
                               (list(RUNTIMES), list(MESSAGE_TYPES), start, PROCESSOR)).fetchone()
        reasons = conn.execute("""select r->>'reason' reason, count(*) n from extraction.segments s,
                                         jsonb_array_elements(s.rejected) r
                                  where s.processor = %s and s.status = 'extracted'
                                    and s.created_at > now() - make_interval(hours => %s) group by 1""",
                               (PROCESSOR, hours)).fetchall()
    return {"v1_start": start.isoformat() if start else None, "threads": q, "segments": s, "backlog": backlog,
            "rejections": reasons}
