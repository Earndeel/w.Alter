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

PROCESSOR, VERSION = "l3.extract", "2"
POSTE = "memory_extraction"          # Walter Router poste: the router picks the model (never hardcoded)
RUNTIMES = ("hermes", "claude_code", "codex", "dsh")
MESSAGE_TYPES = ("message.sent", "message.received")    # sent = the owner, received = the assistant
KINDS = ("fact", "decision", "preference", "goal", "constraint", "commitment", "correction")
OWNER_KINDS = {"decision", "preference", "goal", "constraint", "correction"}
# Stage of an intention (P1.2): a request is not a decision, a decision is not an execution, a report is not a proof.
STAGES = {"decision": {"requested", "proposed", "decided", "executed", "abandoned"},
          "goal": {"requested", "decided", "executed", "abandoned"}, "commitment": {"open", "done"}}
STATES = STAGES                     # P1.1 name
SCOPES = {"durable", "task", "until"}
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

PROMPT = """Tu extrais la mémoire durable d'un extrait de conversation entre Monsieur (le propriétaire) et son assistant W.Alter.

Contexte qui précède (ne pas citer) :
{context}

Connaissances déjà enregistrées (références K) :
{known}

Messages à analyser (numérotés, seuls citables) :
{transcript}

Rends un JSON :
{{"summary": "2 à 5 phrases : de quoi il a été question, ce qui a été décidé ou fait, où on en est",
  "topics": ["..."], "projects": ["..."], "people": ["personnes citées hors Monsieur et W.Alter"],
  "items": [{{"kind": "fact|decision|preference|goal|constraint|commitment|correction",
              "text": "une seule connaissance, autonome et compréhensible sans la conversation",
              "subject": "owner | walter | project:<nom> | person:<nom> | other",
              "stage": "decision/goal : requested|proposed|decided|executed|abandoned ; commitment : open|done ; sinon stated",
              "scope": "durable | task | until", "until": "AAAA-MM-JJ si scope = until, sinon null",
              "msgs": [numéros des messages qui l'établissent],
              "quote": "extrait EXACT (copié mot pour mot, 5 à 25 mots) d'un des messages cités",
              "same_as": "K… si c'est la même connaissance qu'une connaissance déjà enregistrée, sinon null",
              "supersedes": ["K… que celle-ci remplace ou corrige"], "contradicts": ["K… qu'elle contredit sans trancher"],
              "confidence": 0.0}}]}}

Ce qui compte comme connaissance durable :
- étape (stage), sans jamais en sauter une : requested = Monsieur demande ou veut quelque chose ; proposed = W.Alter propose et Monsieur n'a pas tranché ; decided = Monsieur a décidé ou validé ; executed = un message dit que c'est fait (c'est un compte rendu, pas une preuve) ; abandoned = Monsieur y renonce. Une demande de Monsieur est requested, jamais executed ;
- portée (scope) : durable = vaut au-delà du travail en cours ; task = ne vaut que pour le travail en cours (« ne touche pas aux fichiers que Codex modifie », « attends mon accord avant l'étape suivante ») ; until = jusqu'à une date (until) ;
- préférence / contrainte : une règle, un goût, une manière de travailler, une limite à respecter ;
- objectif : ce que Monsieur veut atteindre ; engagement : ce que quelqu'un s'est engagé à faire (open/done) ;
- correction : Monsieur corrige une information ou une erreur ; fait : une information durable sur Monsieur, ses proches, ses projets, son environnement, ou l'architecture et l'état de W.Alter ;
- les choix techniques et d'architecture d'un projet SONT des décisions à garder ; ne garde pas les détails passagers des actions de W.Alter (commandes lancées, erreurs corrigées, essais) sauf s'ils fixent une règle durable ;
- une demande de Monsieur (« tu peux… », « analyse… », « fais… », « envoie ») est un objectif (goal) ou une décision de Monsieur à l'étape requested, même si W.Alter l'exécute aussitôt ;
- une approbation courte de Monsieur (« oui », « vas-y », « envoi », « ok ») d'une proposition de W.Alter est une décision de Monsieur : écris la décision complète et cite à la fois le message de W.Alter qui la propose et celui de Monsieur qui l'approuve ;
- une question de Monsieur qui exprime clairement une attente (« pourquoi tu ne le fais pas toi-même ? ») est une contrainte.
Règles : uniquement ce qui est dit dans les messages numérotés ; une affirmation de W.Alter n'est pas une décision de Monsieur ;
une affirmation d'un tiers n'est pas un fait vérifié (dis « selon … ») ; listes vides si rien de durable ; chaque item cite ses numéros et une citation exacte."""
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:16]


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


def _thread_start(conn, source: str, thread_id: str) -> datetime | None:
    """Eligibility start of a thread: its explicit catch-up start if one was requested, else the V1 start."""
    r = conn.execute("select from_at from extraction.threads where processor = %s and source = %s and thread_id = %s",
                     (PROCESSOR, source, thread_id)).fetchone()
    return r["from_at"] if r and r["from_at"] else v1_start(conn)


def mark_dirty(conn, source: str, thread_id: str, last_event_at=None) -> None:
    conn.execute("""insert into extraction.threads (processor, source, thread_id, status, last_event_at, dirty_since)
                    values (%s, %s, %s, 'dirty', %s, now())
                    on conflict (processor, source, thread_id) do update set
                      last_event_at = greatest(extraction.threads.last_event_at, excluded.last_event_at),
                      status = case when extraction.threads.status = 'working' then 'working' else 'dirty' end,
                      dirty_since = coalesce(extraction.threads.dirty_since, now()), updated_at = now()""",
                 (PROCESSOR, source, thread_id, last_event_at))


def on_bus_events(evs: list[dict]) -> int:
    """Bus consumer handler (memory.event): a new message of a runtime makes its thread dirty. Idempotent."""
    n = 0
    with connection() as conn:
        for ev in evs:
            p = ev.get("payload") or {}
            if p.get("source") in RUNTIMES and p.get("event_type") in MESSAGE_TYPES and p.get("thread_id"):
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
               e.payload->>'model' as model, e.payload->>'cwd' as cwd
        from core.events e
        where e.source = %s and e.thread_id = %s and e.event_type = any(%s)
          and (%s::timestamptz is null or e.ingested_at >= %s::timestamptz)
          and not exists (select 1 from extraction.covered c where c.processor = %s and c.event_id = e.event_id)
          and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                          and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
        order by e.occurred_at, e.event_id""",
                        (source, thread_id, list(MESSAGE_TYPES), start, start, PROCESSOR)).fetchall()


def _context(conn, source: str, thread_id: str, before) -> list[dict]:
    rows = conn.execute("""select e.event_type, e.occurred_at, e.content, e.payload->>'model' as model, e.thread_id,
                                  e.payload->>'cwd' as cwd from core.events e
                           where e.source = %s and e.thread_id = %s and e.event_type = any(%s)
                             and e.occurred_at < %s and e.privacy_class = 'cloud_allowed'
                           order by e.occurred_at desc limit 20""",
                        (source, thread_id, list(MESSAGE_TYPES), before)).fetchall()
    return [r for r in rows if not _noise(r)][:CONTEXT_MSGS][::-1]


def _known(conn, source: str, thread_id: str, text: str) -> list[dict]:
    """Current v2 knowledge the model may restate, supersede or contradict: this thread's latest items and the most
    similar ones anywhere (local embeddings, no model call)."""
    rows = conn.execute("""select item_id::text, kind, content, coalesce(stage, attributes->>'state') as state,
                                  created_at, lineage_id::text, coalesce(valid_from, created_at) as at
                           from core.derived_items where derived_by = %s and status in ('derived','verified')
                             and (valid_to is null or valid_to > now())
                             and generation = 'g1' and kind <> 'summary' and source_refs->>'thread' = %s
                             and source_refs->>'source' = %s
                           order by created_at desc limit %s""",
                        (PROCESSOR, thread_id, source, KNOWN_THREAD)).fetchall()
    try:
        from . import search
        v = search.vec(search.embed([text[:4000]])[0])
        rows += conn.execute("""select d.item_id::text, d.kind, d.content, coalesce(d.stage, d.attributes->>'state') as state,
                                       d.created_at, d.lineage_id::text, coalesce(d.valid_from, d.created_at) as at
                                from search.chunks c join core.derived_items d on d.item_id = c.ref_id
                                where c.kind = 'derived' and c.embedding is not null and d.derived_by = %s
                                  and d.generation = 'g1' and d.status in ('derived','verified') and d.kind <> 'summary'
                                  and (d.valid_to is null or d.valid_to > now())
                                order by c.embedding <=> %s::vector limit %s""",
                             (PROCESSOR, v, KNOWN_SIMILAR)).fetchall()
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


def validate(item: dict, seg: list[dict], known: dict[str, dict]) -> tuple[dict | None, str | None]:
    """→ (clean item, None) or (None, reason). Pure: no database."""
    kind = (item.get("kind") or "").strip().lower()
    text = (item.get("text") or "").strip()
    if kind not in KINDS:
        return None, "bad_kind"
    if len(text) < 8:
        return None, "empty_text"
    nums = item.get("msgs") or []
    if not isinstance(nums, list) or not nums or not all(isinstance(n, int) and 1 <= n <= len(seg) for n in nums):
        return None, "invalid_citation"
    cited = [seg[n - 1] for n in sorted(set(nums))]
    if not quote_found(item.get("quote") or "", [m["content"] or "" for m in cited]):
        return None, "quote_not_found"
    by_owner = any(m["event_type"] == "message.sent" for m in cited)
    by_agent = any(m["event_type"] == "message.received" for m in cited)
    stage = (item.get("stage") or item.get("state") or "stated").strip().lower()
    if kind in STAGES:
        if stage not in STAGES[kind]:
            stage = "requested" if kind in ("decision", "goal") else "open"
    else:
        stage = "stated"
    if kind in OWNER_KINDS and not by_owner and not (kind == "decision" and stage == "proposed"):
        return None, "no_owner_evidence"          # a W.Alter proposal is kept as proposed, never as the owner's choice
    if stage in ("decided", "requested", "abandoned") and not by_owner:
        stage = "proposed"
    if stage == "executed" and not by_agent:      # "it is done" needs a report of it; the owner's request is not one
        stage = "decided" if by_owner else "proposed"
    scope = (item.get("scope") or "durable").strip().lower()
    scope = scope if scope in SCOPES else "durable"
    until = None
    if scope == "until":
        try:
            until = datetime.fromisoformat(str(item.get("until"))[:10]).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            scope = "task"
    state = stage
    refs = lambda key: [k for k in (item.get(key) or []) if isinstance(k, str) and k in known]
    same = item.get("same_as") if isinstance(item.get("same_as"), str) and item.get("same_as") in known else None
    supersedes, contradicts = refs("supersedes"), refs("contradicts")
    if supersedes and not by_owner:          # only the owner's word replaces knowledge; otherwise flag the conflict
        contradicts, supersedes = contradicts + supersedes, []
    try:
        conf = max(0.0, min(1.0, float(item.get("confidence") or 0.7)))
    except (TypeError, ValueError):
        conf = 0.7
    return {"kind": kind, "text": text, "state": state, "stage": stage, "scope": scope, "until": until,
            "subject": (item.get("subject") or "other")[:120],
            "quote": (item.get("quote") or "")[:400], "cited": cited, "by_owner": by_owner,
            "epistemic": "owner_stated" if by_owner else "agent_reported",
            "epistemic_v": "stated_owner" if by_owner else "agent_reported", "same_as": same,
            "supersedes": supersedes, "contradicts": contradicts, "confidence": conf}, None


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
    who = "Monsieur" if m["event_type"] == "message.sent" else "W.Alter"
    from .views import INJECTED
    text = RUNTIME_NOTES.sub("", INJECTED.sub("", m["content"] or "")).strip()[:MSG_CHARS]
    return f"{prefix}{i}. [{who} · {m['occurred_at']:%Y-%m-%d %H:%M}] {text}"


def extract_segment(source: str, thread_id: str, seg: list[dict], *, chat=None, budget: str = "recurring",
                    backfill: str | None = None) -> dict:
    """One model call for a segment of cloud-readable, non-noise messages; writes items + coverage atomically.
    backfill: the tag of a selective catch-up of pre-V1 messages (backfill()): the segment's summary is not stored
    (fragments of an old conversation, not a summary of it) and the items carry attributes.backfill = tag."""
    chat = chat or llm.chat
    with connection() as conn:
        context = _context(conn, source, thread_id, seg[0]["occurred_at"])
        known_rows = _known(conn, source, thread_id, "\n".join((m["content"] or "")[:500] for m in seg))
    known = {f"K{i + 1}": r for i, r in enumerate(known_rows)}
    seg_class = privacy.strictest(*(m["privacy_class"] for m in seg))
    prompt = PROMPT.format(
        context="\n".join(_line(i + 1, m, "C") for i, m in enumerate(context)) or "(début de conversation)",
        known="\n".join(f"{k}. [{r['kind']}{'/' + r['state'] if r['state'] and r['state'] != 'stated' else ''}] {r['content']}"
                        for k, r in known.items()) or "(aucune)",
        transcript="\n".join(_line(i + 1, m) for i, m in enumerate(seg)))
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
        item, why = validate(raw, seg, known)
        if why:
            rejected.append({"reason": why, "item": {k: raw.get(k) for k in ("kind", "text", "msgs", "quote")}})
        else:
            kept.append(item)
    out = {"items": 0, "reused": 0, "superseded": 0, "rejected": len(rejected), "cost_usd": float(res.get("cost_usd") or 0)}
    with connection() as conn:
        status = "extracted" if kept or data.get("summary") else "empty"
        sid = _segment_row(conn, source=source, thread_id=thread_id, status=status, msgs=seg, rejected=rejected,
                           model=res.get("model"), cost=res.get("cost_usd"), usage=res.get("usage"), latency_ms=latency)
        base_refs = {"segment": sid, "thread": thread_id, "source": source}
        if data.get("summary") and not backfill:
            conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                processor_version, model, prompt_hash, source_event_ids, source_refs, valid_from, privacy_class,
                                generation)
                            values ('summary', %s, %s, 'derived', %s, %s, %s, %s, %s::uuid[], %s, %s, %s, 'g1')""",
                         (data["summary"], json.dumps({"topics": data.get("topics") or [], "projects": data.get("projects") or [],
                                                       "people": data.get("people") or [], "from": str(seg[0]["occurred_at"]),
                                                       "to": str(seg[-1]["occurred_at"]), "pipeline": "v1"}, ensure_ascii=False),
                          PROCESSOR, VERSION, res.get("model"), PROMPT_HASH, [str(m["event_id"]) for m in seg],
                          json.dumps({**base_refs, "ref": f"{sid}:summary"}), seg[-1]["occurred_at"], seg_class))
        for k, it in enumerate(kept):
            ev_ids = [str(m["event_id"]) for m in it["cited"]]
            if it["same_as"]:            # same knowledge again: new evidence on the known item, no duplicate
                target = known[it["same_as"]]["item_id"]
                conn.execute("""update core.derived_items set source_event_ids = (select array_agg(distinct x)
                                    from unnest(source_event_ids || %s::uuid[]) x) where item_id = %s""", (ev_ids, target))
                for e in ev_ids:
                    conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                                    values ('derived_items', %s, 'event', %s, 'supports') on conflict do nothing""", (target, e))
                out["reused"] += 1
                continue
            cls = privacy.strictest(*(m["privacy_class"] for m in it["cited"]))
            attrs = {"subject": it["subject"], "state": it["state"], "epistemic": it["epistemic"], "quote": it["quote"],
                     "projects": data.get("projects") or [], "pipeline": "v1"}
            if backfill:
                attrs["backfill"] = backfill
            if it["kind"] == "commitment":
                attrs["holder"] = "owner" if it["by_owner"] else "walter"
            if it["contradicts"]:
                attrs["contested"] = True
            lineage = known[it["supersedes"][0]].get("lineage_id") if it["supersedes"] else None
            new_id = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                         processor_version, model, prompt_hash, source_event_ids, source_refs, valid_from,
                                         confidence, privacy_class, generation, lineage_id, epistemic, stage, scope,
                                         valid_to)
                                     values (%s, %s, %s, 'derived', %s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s, 'g1',
                                             %s, %s, %s, %s, %s)
                                     on conflict (derived_by, (source_refs->>'ref')) where source_refs ? 'ref' do nothing
                                     returning item_id::text""",
                                  (it["kind"], it["text"], json.dumps(attrs, ensure_ascii=False), PROCESSOR, VERSION,
                                   res.get("model"), PROMPT_HASH, ev_ids, json.dumps({**base_refs, "ref": f"{sid}:{k}"}),
                                   it["cited"][-1]["occurred_at"], it["confidence"], cls, lineage, it["epistemic_v"],
                                   it["stage"], it["scope"], it["until"])).fetchone()
            if not new_id:
                continue
            new_id = new_id["item_id"]
            out["items"] += 1
            stated_at = it["cited"][-1]["occurred_at"]
            newer = [ref for ref in it["supersedes"] if known[ref].get("at") and known[ref]["at"] > stated_at]
            if newer:      # a replayed older message never replaces newer knowledge: it is that knowledge's past
                ref = newer[0]
                conn.execute("""update core.derived_items set status = 'superseded', valid_to = %s, lineage_id = %s::uuid,
                                  attributes = attributes || jsonb_build_object('superseded_by', %s::text,
                                                                               'replayed_older', true)
                                where item_id = %s""", (known[ref]["at"], known[ref].get("lineage_id"),
                                                        known[ref]["item_id"], new_id))
                it["supersedes"] = [r for r in it["supersedes"] if r not in newer]
            for ref in it["supersedes"]:
                old = known[ref]["item_id"]
                done = conn.execute("""update core.derived_items set status = 'superseded', valid_to = %s,
                                           attributes = attributes || jsonb_build_object('superseded_by', %s::text)
                                       where item_id = %s and status in ('derived','verified') returning item_id""",
                                    (it["cited"][-1]["occurred_at"], new_id, old)).fetchone()
                if done:
                    out["superseded"] += 1
                    out.setdefault("changed", []).append(old)
                    conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                                    values ('derived_items', %s, 'derived', %s, 'supersedes') on conflict do nothing""",
                                 (new_id, old))
            older_than = [ref for ref in it["contradicts"] if known[ref].get("at") and known[ref]["at"] > stated_at]
            if older_than:   # an older statement replayed now is the past of newer knowledge, never a doubt on it
                ref = older_than[0]
                conn.execute("""update core.derived_items set status = 'superseded', valid_to = %s,
                                  attributes = attributes || jsonb_build_object('superseded_by', %s::text,
                                                                               'replayed_older', true)
                                where item_id = %s""", (known[ref]["at"], known[ref]["item_id"], new_id))
                it["contradicts"] = [r for r in it["contradicts"] if r not in older_than]
            for ref in it["contradicts"]:
                old = known[ref]["item_id"]
                out.setdefault("changed", []).append(old)
                conn.execute("""update core.derived_items set attributes = attributes || '{"contested": true}'
                                where item_id = %s""", (old,))
                conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                                values ('derived_items', %s, 'derived', %s, 'contradicts') on conflict do nothing""",
                             (new_id, old))
        conn.execute("update extraction.segments set items = %s, reused = %s, superseded = %s where segment_id = %s",
                     (out["items"], out["reused"], out["superseded"], sid))
    try:   # P1.2: the consolidated views built on this thread are rebuilt from the new state (targeted invalidation);
        # P1.6: a replaced or contested item also marks the episodes and periods that list it (and their parents)
        from . import consolidate
        consolidate.invalidate(threads=[(source, thread_id)], item_ids=out.pop("changed", None))
        from . import entities
        entities.link_items(conn_items_of_segment(sid))
    except Exception as e:
        log.warning("view invalidation / entity links failed (extraction kept): %s", e)
    out["segment_id"] = sid
    return out


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
    if (mode or policy()) == "adaptive":
        segs, tail, out["reason"] = adaptive_due(usable, now)
    else:
        segs, tail = due_segments(usable, now)
    if force and tail:
        segs, tail = segs + [tail], []
    out["waiting"] = len(tail)
    for seg in segs:
        if not any(m["event_type"] == "message.sent" for m in seg) and sum(_size(m) for m in seg) < 1500:
            with connection() as conn:   # assistant-only chatter: nothing the owner said, nothing substantial
                _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=seg,
                             rejected=[{"reason": "no_owner_message"}])
            out["filtered"] += len(seg)
            continue
        r = extract_segment(source, thread_id, seg, chat=chat, budget=budget)
        out["segments"] += 1
        for k in ("items", "reused", "superseded", "rejected"):
            out[k] += r[k]
        out["cost_usd"] += r["cost_usd"]
    return out


# ───────────────────────────── the worker ─────────────────────────────
def claim(limit: int = 8) -> list[dict]:
    """Lease due dirty threads (short transaction: no lock is held during model calls)."""
    with connection() as conn:
        return conn.execute("""
            update extraction.threads t set status = 'working', claimed_at = now(), updated_at = now()
            where (t.processor, t.source, t.thread_id) in (
                select processor, source, thread_id from extraction.threads
                where processor = %s and (status = 'dirty' or (status = 'working' and claimed_at < now() - %s))
                  and (retry_after is null or retry_after <= now())
                order by last_event_at nulls first limit %s for update skip locked)
            returning t.source, t.thread_id, t.attempts""", (PROCESSOR, LEASE, limit)).fetchall()


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


def tick(limit: int = 8, workers: int = 4, chat=None, budget: str = "recurring") -> dict:
    import concurrent.futures as cf
    total = {"threads": 0, "segments": 0, "items": 0, "reused": 0, "superseded": 0, "rejected": 0, "filtered": 0,
             "local_only": 0, "cost_usd": 0.0, "errors": 0}
    from . import organic
    if organic.extraction_paused():      # nothing claimed: dirty threads stay pending until the pause ends
        return {**total, "paused": True}
    claimed = claim(limit)

    def one(t):
        try:
            r = process_thread(t["source"], t["thread_id"], chat=chat, budget=budget)
            _release(t["source"], t["thread_id"], waiting=r["waiting"] > 0)
            return r
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


def backfill(event_ids: list[str], *, tag: str, chat=None, budget: str = "backfill", window: int = 1,
             max_threads: int | None = None, workers: int = 4, dry: bool = False) -> dict:
    """Selective catch-up of pre-V1 history (g0 → g1 migration, 2026-11-10): only the given messages, each with
    `window` neighbours on either side in its thread (the assistant turn an approval answers), go through the same
    extraction as live messages (same prompt, validation, supersession, privacy, entity links, view invalidation).
    Idempotent: covered events are never redone (extraction.covered). Reversible: every segment is listed under
    extraction.state['backfill:<tag>'] and backfill_revert(tag) retracts what it produced. Pre-V1 messages are never
    swept: only an explicit call reaches them."""
    from collections import defaultdict
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
           "superseded": 0, "rejected": 0, "filtered": 0, "skipped_covered": 0, "events": 0, "cost_usd": 0.0,
           "errors": 0, "busy": 0}

    def one(key):
        source, thread_id = key
        res = {k: 0 for k in ("segments", "items", "reused", "superseded", "rejected", "filtered", "events",
                              "skipped_covered", "errors", "busy")}
        res["cost_usd"], res["segment_ids"] = 0.0, []
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
        segs, cur, size = [], [], 0
        for m in usable:
            if cur and size + _size(m) > SEGMENT_CHARS:
                segs.append(cur); cur, size = [], 0
            cur.append(m); size += _size(m)
        if cur:
            segs.append(cur)
        for seg in segs:
            if not any(m["event_type"] == "message.sent" for m in seg):
                with connection() as conn:
                    sid = _segment_row(conn, source=source, thread_id=thread_id, status="filtered", msgs=seg,
                                       rejected=[{"reason": "no_owner_message"}])
                res["filtered"] += len(seg)
                res["segment_ids"].append(str(sid))
                continue
            with connection() as conn:   # keep the lease while this thread's segments go through
                conn.execute("""update extraction.threads set claimed_at = now() where processor = %s and source = %s
                                and thread_id = %s and status = 'working'""", (PROCESSOR, source, thread_id))
            try:
                r = extract_segment(source, thread_id, seg, chat=chat, budget=budget, backfill=tag)
            except Exception as e:  # noqa: BLE001 — this thread is retried by a later run (nothing covered)
                log.warning("backfill %s %s: %s", source, thread_id, e)
                res["errors"] += 1
                continue
            res["segments"] += 1
            res["segment_ids"].append(str(r["segment_id"]))
            for k in ("items", "reused", "superseded", "rejected"):
                res[k] += r[k]
            res["cost_usd"] += r["cost_usd"]
        return res

    from concurrent.futures import ThreadPoolExecutor
    seg_ids: list[str] = []
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for res in ex.map(one, threads):
            seg_ids += res.pop("segment_ids")
            for k, v in res.items():
                out[k] += v
            if seg_ids and not dry:     # the ledger is written as it goes: an interrupted run stays revertible
                with connection() as conn:
                    conn.execute("""insert into extraction.state (key, value) values (%s, %s)
                                    on conflict (key) do update set value = jsonb_set(extraction.state.value,
                                      '{segments}', (select coalesce(jsonb_agg(distinct x), '[]'::jsonb) from
                                        jsonb_array_elements_text(coalesce(extraction.state.value->'segments', '[]'::jsonb)
                                                                  || (excluded.value->'segments')) x)),
                                      updated_at = now()""",
                                 (f"backfill:{tag}", json.dumps({"tag": tag, "segments": seg_ids})))
    out["cost_usd"] = round(out["cost_usd"], 4)
    return out


def backfill_revert(tag: str, *, confirm: bool = False) -> dict:
    """Undo backfill(tag): its items are retracted (and their chunks hidden), what they had superseded is current
    again, its events are uncovered (a later backfill may redo them). Dry run unless confirm."""
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
        out = {"tag": tag, "segments": len(segs), "items": len(items), "revived": len(revived),
               "uncontested": len(contested), "executed": confirm,
               "kept": "evidence added to existing items by same_as (true evidence) is kept"}
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
