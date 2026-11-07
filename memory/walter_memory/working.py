"""Working memory of a conversation (Memory V1 P1.1): what a model must not lose, rebuilt from Memory at any moment.

The state of a thread is a projection, never a second store, so it survives a context compression and is the same
from any runtime:
  - interpreted: the current V1 knowledge (g1, extract2) of the thread and of the threads attached to the same subject
    (another runtime working on the same thing): objective, constraints, preferences, decisions, open commitments,
    corrections;
  - pending: every owner message not interpreted yet, VERBATIM (uncovered by extract2, or covered without
    interpretation: local_only for a local audience, failed) — nothing the owner said waits silently for a model;
  - plan: the agent's own plan, read without a model from its plan tool calls in walter_logs;
  - question: the agent's last message when it ends on a question.
Deterministic and model-free (a few SQL queries). Audience rules as everywhere: a cloud audience only gets
cloud_allowed evidence; the state's class is the strictest of what it contains.

  state(source, thread_id, audience="cloud_model", at=None, subject=True) -> dict
  render(state) -> str            the block Context injects (layer 2, SessionState)
  session_state(st) -> dict       the walter-context SessionState v1 fields (+ pending, question)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone

from . import privacy
from .db import connection

KINDS = ("goal", "constraint", "preference", "decision", "commitment", "correction", "fact")
TITLES = {"goal": "Objectif", "constraint": "Contraintes en vigueur", "preference": "Préférences",
          "decision": "Décisions", "commitment": "Engagements ouverts", "correction": "Corrections",
          "fact": "Faits récents"}
# Rules and aims stay whole (they are what a model must not lose); decisions and commitments keep the most recent.
PER_KIND = {"goal": 40, "constraint": 60, "preference": 40, "correction": 40, "decision": 25, "commitment": 15,
            "fact": 10}
PENDING_MAX, PENDING_CHARS = 12, 2000
RECENT_UNCITED = timedelta(hours=24)  # an owner message read by extraction but cited by no knowledge stays verbatim 24 h
ACK = re.compile(r"(?i)^\s*(ok+|merci|ok merci|top|parfait|super|nickel|cool)[\s!.,]*$")   # never "oui"/"vas-y": approvals
SUBJECT_WINDOW = timedelta(days=14)
PLAN_TOOLS = ("mcp__ccd_turn__update_plan", "TodoWrite", "update_plan")


SUBJECT_GUESS, GUESS_MARGIN = 0.5, 0.1   # a new session's first message: its subject by local similarity, only if clear


def _guess_subject(conn, message: str, at) -> dict | None:
    """The subject a session not attached yet most likely continues (another runtime picking up the work): the
    closest active subject by local embedding, only when it is clearly closer than the next one. No model call."""
    from . import views
    from .search import embed
    rows = views.candidates(conn, {"message": message, "at": at or datetime.now(timezone.utc)}, embed)
    if not rows or rows[0]["sim"] < SUBJECT_GUESS or (len(rows) > 1 and rows[0]["sim"] - rows[1]["sim"] < GUESS_MARGIN):
        return None
    return {"key": rows[0]["view_key"], "title": rows[0]["title"], "similarity": round(float(rows[0]["sim"]), 3)}


def _threads(conn, source: str, thread_id: str, subject: bool, message: str = "", at=None,
             guess: dict | None = None) -> list[tuple[str, str]]:
    """This thread, plus the threads of other sessions attached to the same subject view recently (or to the subject
    a not-yet-attached session's message most likely continues: `guess` receives it)."""
    out = [(source, thread_id)]
    if not subject:
        return out
    attached = conn.execute("select 1 from views.member where session_id like %s limit 1", (f"%/{thread_id}",)).fetchone()
    if not attached and message.strip():
        g = _guess_subject(conn, message, at)
        if g:
            if guess is not None:
                guess.update(g)
            rows = conn.execute("""select distinct split_part(session_id, '/', 1) as source,
                                          split_part(session_id, '/', 3) as thread_id
                                   from views.member where view_key = %s and occurred_at > now() - %s""",
                                (g["key"], SUBJECT_WINDOW)).fetchall()
            out += [(r["source"], r["thread_id"]) for r in rows if r["thread_id"]]
        return list(dict.fromkeys(out))
    rows = conn.execute("""
        select distinct split_part(m2.session_id, '/', 1) as source, split_part(m2.session_id, '/', 3) as thread_id
        from views.member m1 join views.member m2 on m2.view_key = m1.view_key
        where m1.session_id like %s and m2.occurred_at > now() - %s and m2.session_id <> m1.session_id""",
                        (f"%/{thread_id}", SUBJECT_WINDOW)).fetchall()
    out += [(r["source"], r["thread_id"]) for r in rows if r["thread_id"]]
    return list(dict.fromkeys(out))


def _interpreted(conn, threads, allowed, at):
    rows = conn.execute("""
        select item_id::text, kind, content, attributes, created_at, valid_from, privacy_class, lineage_id::text,
               coalesce(stage, attributes->>'state') as stage, scope,
               coalesce(epistemic, case attributes->>'epistemic' when 'owner_stated' then 'stated_owner'
                                   else attributes->>'epistemic' end) as epistemic,
               source_refs->>'thread' as thread, source_refs->>'source' as source
        from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind = any(%s)
          and status in ('derived', 'verified') and privacy_class = any(%s)
          and (valid_to is null or valid_to > coalesce(%s::timestamptz, now()))
          and (source_refs->>'source', source_refs->>'thread') in (select * from unnest(%s::text[], %s::text[]))
          and (%s::timestamptz is null or created_at <= %s::timestamptz)
        order by created_at""",
                        (list(KINDS), allowed, at, [s for s, _ in threads], [t for _, t in threads], at, at)).fetchall()
    out = {k: [] for k in KINDS}
    for r in rows:
        if r["stage"] in ("abandoned", "done"):
            continue
        out[r["kind"]].append({"id": r["item_id"], "text": r["content"], "state": r["stage"], "stage": r["stage"],
                               "scope": r["scope"], "epistemic": r["epistemic"], "lineage": r["lineage_id"],
                               "replaced": ((r["attributes"] or {}).get("replacement_proposed") or {}).get("by"),
                               "at": r["valid_from"] or r["created_at"],
                               "privacy_class": r["privacy_class"], "thread": r["thread"]})
    return {k: v[-PER_KIND[k]:] for k, v in out.items()}


def _pending(conn, threads, allowed, at):
    """Owner messages not interpreted yet, verbatim. In a replay (`at`), coverage written after `at` does not count."""
    from .extract2 import MESSAGE_TYPES, PROCESSOR, RUNTIME_NOTES, _noise
    from .views import INJECTED
    v1 = conn.execute("select (value->>'at')::timestamptz as at from extraction.state where key = 'v1_start'").fetchone()
    rows = []
    for source, thread in threads:      # one indexed scan per thread (core.events (source, thread_id, occurred_at))
        start = conn.execute("""select from_at from extraction.threads where processor = %s and source = %s
                                and thread_id = %s""", (PROCESSOR, source, thread)).fetchone()
        since = (start and start["from_at"]) or (v1 and v1["at"])
        rows += conn.execute("""
            select e.event_id::text, e.event_type, e.occurred_at, e.content, e.privacy_class, e.thread_id, e.source,
                   e.payload->>'model' as model, e.payload->>'cwd' as cwd
            from core.events e
            where e.source = %s and e.thread_id = %s and e.event_type = 'message.sent' and e.privacy_class = any(%s)
              and (%s::timestamptz is null or e.ingested_at >= %s::timestamptz)
              and (%s::timestamptz is null or e.ingested_at <= %s::timestamptz)
              and e.occurred_at >= coalesce(%s::timestamptz, now()) - interval '30 days'   -- partition pruning
              and not exists (select 1 from core.derived_items d          -- interpreted = cited by some V1 knowledge
                              where d.generation = 'g1' and d.derived_by = %s and d.kind <> 'summary'
                                and d.source_event_ids @> array[e.event_id]
                                and (%s::timestamptz is null or d.created_at <= %s::timestamptz))
              and not exists (select 1 from core.events r where r.event_type = 'event.retracted'
                              and r.payload @> jsonb_build_object('target_event_id', e.event_id::text))
            order by e.occurred_at desc limit 60""",
                             (source, thread, allowed, since, since, at, at, since, PROCESSOR, at, at)).fetchall()
        read = {r["event_id"] for r in conn.execute("""
            select c.event_id::text from extraction.covered c join extraction.segments s on s.segment_id = c.segment_id
            where c.processor = %s and c.event_id = any(%s::uuid[]) and s.status in ('extracted', 'empty')
              and (%s::timestamptz is null or s.created_at <= %s::timestamptz)""",
                                                          (PROCESSOR, [r["event_id"] for r in rows], at, at))}
        for r in rows:
            r["read"] = r["event_id"] in read
    rows.sort(key=lambda r: r["occurred_at"], reverse=True)
    out = []
    now = at or datetime.now(timezone.utc)
    for r in rows:
        if _noise(r):
            continue
        text = RUNTIME_NOTES.sub("", INJECTED.sub("", r["content"] or "")).strip()
        if not text or (r["read"] and ACK.match(text)):
            continue                      # read, nothing in it ("ok merci")
        if r["read"] and now - r["occurred_at"] > RECENT_UNCITED:
            continue                      # read long ago and cited by nothing: still in memory (events, search)
        cut = len(text) > PENDING_CHARS
        out.append({"event_id": r["event_id"], "at": r["occurred_at"], "source": r["source"], "thread": r["thread_id"],
                    "privacy_class": r["privacy_class"], "read": r["read"],
                    "text": text[:PENDING_CHARS] + (f" […] (texte intégral : événement {r['event_id']})" if cut else "")})
        if len(out) >= PENDING_MAX:
            break
    return out[::-1]


def _plan(conn, threads, at):
    """The agent's current plan from its plan tool calls (claude_code update_plan / TodoWrite), no model."""
    sess = [r["session_id"] for r in conn.execute(
        "select session_id from walter_logs.sessions where native_id = any(%s)", ([t for _, t in threads],))]
    if not sess:
        return None
    rows = conn.execute("""
        select tool, text, occurred_at from walter_logs.events
        where session_id = any(%s) and type = 'tool/call' and tool = any(%s)
          and (%s::timestamptz is null or occurred_at <= %s::timestamptz)
        order by occurred_at desc limit 40""", (sess, list(PLAN_TOOLS), at, at)).fetchall()
    ops = []
    for r in rows:
        try:
            args = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        ops.append(args)
        if "items" in args or "todos" in args or "plan" in args:
            break
    if not ops or not any(k in ops[-1] for k in ("items", "todos", "plan")):
        return None
    base = ops[-1]
    items = [{"content": i.get("content") or i.get("step") or "", "status": i.get("status", "pending")}
             for i in (base.get("items") or base.get("todos") or base.get("plan") or []) if isinstance(i, dict)]
    for op in reversed(ops[:-1]):          # later updates, oldest first
        cur = next((k for k, i in enumerate(items) if i["status"] == "in_progress"), None)
        if op.get("advance") and cur is not None:
            items[cur]["status"] = "completed"
            nxt = next((k for k in range(cur + 1, len(items)) if items[k]["status"] == "pending"), None)
            if nxt is not None:
                items[nxt]["status"] = "in_progress"
        for d in op.get("done") or []:
            if isinstance(d, int) and 1 <= d <= len(items):
                items[d - 1]["status"] = "completed"
        if isinstance(op.get("start"), int) and 1 <= op["start"] <= len(items):
            for i in items:
                if i["status"] == "in_progress":
                    i["status"] = "pending" if i is not items[op["start"] - 1] else i["status"]
            items[op["start"] - 1]["status"] = "in_progress"
    return items


def _last_owner(source: str, thread_id: str, allowed, at) -> dict | None:
    """The owner's latest message in this thread, verbatim (capped), whatever its interpretation state."""
    from .extract2 import RUNTIME_NOTES, _noise
    from .views import INJECTED
    with connection() as conn:
        rows = conn.execute("""select event_id::text, event_type, occurred_at, content, privacy_class, thread_id, source,
                                      payload->>'model' as model, payload->>'cwd' as cwd
                               from core.events where source = %s and thread_id = %s and event_type = 'message.sent'
                                 and privacy_class = any(%s) and (%s::timestamptz is null or ingested_at <= %s::timestamptz)
                                 and occurred_at >= coalesce(%s::timestamptz, now()) - interval '30 days'
                               order by occurred_at desc limit 5""", (source, thread_id, allowed, at, at, at)).fetchall()
    for r in rows:
        if _noise(r):
            continue
        text = RUNTIME_NOTES.sub("", INJECTED.sub("", r["content"] or "")).strip()
        if text:
            return {"event_id": r["event_id"], "at": r["occurred_at"], "source": r["source"], "thread": r["thread_id"],
                    "privacy_class": r["privacy_class"],
                    "text": text[:600] + (f" […] (texte intégral : événement {r['event_id']})" if len(text) > 600 else "")}
    return None


def _question(conn, threads, allowed, at):
    r = conn.execute("""
        select content, occurred_at from core.events
        where event_type = 'message.received' and privacy_class = any(%s)
          and (source, thread_id) = (%s, %s) and (%s::timestamptz is null or ingested_at <= %s::timestamptz)
          and occurred_at >= coalesce(%s::timestamptz, now()) - interval '30 days'
        order by occurred_at desc limit 1""", (allowed, threads[0][0], threads[0][1], at, at, at)).fetchone()
    if not r or not (r["content"] or "").rstrip().endswith("?"):
        return None
    text = r["content"].strip()
    return text[-400:] if len(text) > 400 else text


def state(source: str, thread_id: str, *, audience: str = "cloud_model", at: datetime | None = None,
          subject: bool = True, message: str = "") -> dict:
    t0 = time.perf_counter()
    allowed = privacy.allowed_classes("local_only" if audience == "owner_local" else "cloud_allowed")
    guess: dict = {}
    with connection() as conn:
        threads = _threads(conn, source, thread_id, subject, message, at, guess)
        st = {"source": source, "thread_id": thread_id, "threads": threads, "audience": audience,
              "subject_guess": guess or None,
              "at": (at or datetime.now(timezone.utc)).isoformat(),
              "interpreted": _interpreted(conn, threads, allowed, at),
              "pending": _pending(conn, threads, allowed, at),
              "plan": _plan(conn, threads, at), "question": _question(conn, threads, allowed, at)}
    classes = [i["privacy_class"] for v in st["interpreted"].values() for i in v] + \
              [p["privacy_class"] for p in st["pending"]]
    last = _last_owner(source, thread_id, allowed, at)
    if last and all(p["event_id"] != last["event_id"] for p in st["pending"]):
        st["pending"].append({**last, "read": True, "last": True})
        classes_last = [last["privacy_class"]]
    else:
        classes_last = []
    classes += classes_last
    st["privacy_class"] = privacy.strictest(*classes) if classes else "cloud_allowed"
    st["text"] = render(st)
    st["tokens"] = len(st["text"]) // 4
    st["build_ms"] = round((time.perf_counter() - t0) * 1000)
    return st


# Token budget per category (P1.2 densification). Rules (constraints, preferences, corrections) and the owner's
# pending words are never cut silently: an item that does not fit is replaced by an explicit line with its id.
BUDGET = {"goal": 100, "constraint": 400, "preference": 120, "correction": 100, "decision": 200, "commitment": 100,
          "fact": 60, "plan": 100, "question": 60, "pending": 350}
ITEM_CHARS = 170                  # compact form of an item; the cut is marked with the item's reference
STAGE_TAG = {"requested": "demandé", "proposed": "proposé, non validé", "decided": "validé",
             "executed": "exécution rapportée", "verified": "résultat vérifié", "open": "", "stated": ""}
DUP = 0.9                         # cosine between two items of a category above which they say the same thing


def _tok(text: str) -> int:
    return len(text) // 4 + 1


def _same(a: str, b: str, cos: float) -> bool:
    """Two items say the same thing: close meaning AND mostly the same words AND the same numbers (dates, amounts,
    versions). Similar-looking rules that differ by a word or a number are never merged."""
    if cos < DUP:
        return False
    wa, wb = set(re.findall(r"\w{3,}", a.lower())), set(re.findall(r"\w{3,}", b.lower()))
    if not wa or not wb or len(wa & wb) / len(wa | wb) < 0.6:
        return False
    return sorted(re.findall(r"\d+", a)) == sorted(re.findall(r"\d+", b))


def densify(items: list[dict]) -> list[dict]:
    """Near-duplicates of a category (local embeddings + word and number checks, no model) collapse into the most
    recent, which lists the others (×N and their ids): repetition shrinks, nothing disappears."""
    if len(items) < 2:
        return items
    try:
        from .search import embed
        vecs = embed([i["text"][:400] for i in items])
    except Exception:
        return items
    keep: list[int] = []
    for k in range(len(items) - 1, -1, -1):         # newest first wins
        twin = next((j for j in keep if _same(items[k]["text"], items[j]["text"], float(vecs[k] @ vecs[j]))), None)
        if twin is not None:
            items[twin].setdefault("also", []).append(items[k]["id"])
            continue
        keep.append(k)
    return [items[k] for k in sorted(keep)]


def _compact(text: str, ref: str) -> str:
    text = " ".join(text.split())
    if len(text) <= ITEM_CHARS:
        return text
    cut = text[:ITEM_CHARS]
    stop = max(cut.rfind(" ; "), cut.rfind(". "), cut.rfind(", "))
    return (cut[:stop] if stop > ITEM_CHARS // 2 else cut.rsplit(" ", 1)[0]).rstrip(" ,;.") + f"… [{ref[:8]}]"


def _line(i: dict) -> str:
    tag = STAGE_TAG.get(i.get("stage") or "", "")
    bits = [b for b in (tag, "tâche en cours" if i.get("scope") == "task" else "",
                        "rapporté par l'agent" if i.get("epistemic") == "agent_reported" and i.get("stage") != "proposed" else "",
                        f"×{len(i['also']) + 1} : aussi {', '.join(x[:8] for x in i['also'][:3])}" if i.get("also") else "",
                        f"peut-être remplacé par {i['replaced'][:8]}, à confirmer" if i.get("replaced") else "") if b]
    return f"- {_compact(i['text'], i['id'])}" + (f" [{', '.join(bits)}]" if bits else "") + f" ({i['at']:%d/%m})"


def _fit(lines_items: list[tuple[str, str]], budget: int, essential: bool,
         seen: list | None = None) -> tuple[list[str], list[str]]:
    """Newest-last list → the lines that fit (most recent kept), and the ids left out (never silent)."""
    shown, used, left = [], 0, []
    for line, ref in reversed(lines_items):
        if used + _tok(line) <= budget:
            shown.append(line); used += _tok(line)
            if seen is not None:
                seen.append(ref)
        elif essential and len(line) > 240 and used + _tok(line[:220]) + 8 <= budget:
            shown.append(line[:220].rstrip() + f"… [suite : {ref}]"); used += _tok(line[:220]) + 8
            if seen is not None:
                seen.append(ref)
        else:
            left.append(ref)
    return shown[::-1], left


def render(st: dict, budget: dict | None = None, shown: list | None = None) -> str:
    """The state as Context would inject it: per-category token budget, near-duplicates collapsed, explicit overflow
    lines (ids to fetch) instead of silent truncation. budget=None → BUDGET; {} → no limit."""
    b = BUDGET if budget is None else budget
    lines = []
    for kind in KINDS:
        items = densify(list(st["interpreted"].get(kind) or []))
        if not items:
            continue
        pairs = [(_line(i), i["id"]) for i in items]
        seen: list = []
        shown_lines, left = _fit(pairs, b.get(kind, 10 ** 9), kind in ("constraint", "preference", "correction", "goal"), seen)
        if shown is not None:   # the ids actually given to the model, collapsed duplicates included
            shown += seen + [x for i in items if i["id"] in seen for x in i.get("also", [])]
        shown_ = shown_lines
        lines.append(f"{TITLES[kind]} :")
        lines += shown_
        if left:
            lines.append(f"- (+{len(left)} autres, non affichés faute de place : memory_view details, ids {', '.join(x[:8] for x in left[:6])}"
                         f"{'…' if len(left) > 6 else ''})")
    if st.get("plan"):
        marks = {"completed": "fait", "in_progress": "en cours", "pending": "à faire"}
        plan = [(f"- [{marks.get(i['status'], i['status'])}] {i['content']}", "plan") for i in st["plan"]]
        plan_lines, left = _fit(plan, b.get("plan", 10 ** 9), False)
        lines.append("Plan de l'agent :")
        lines += plan_lines + ([f"- (+{len(left)} étapes antérieures)"] if left else [])
    if st.get("question"):
        lines.append(f"Dernière question de l'agent, sans réponse interprétée : « {st['question'][-400:]} »")
    if st["pending"]:
        new = [p for p in st["pending"] if not p.get("read")]
        old = [p for p in st["pending"] if p.get("read")]
        last = [p for p in old if p.get("last")]
        old = [p for p in old if not p.get("last")]
        for title, group in (("Consignes de Monsieur pas encore interprétées (mot pour mot, à respecter) :", new),
                             ("Messages récents de Monsieur sans connaissance extraite (mot pour mot) :", old),
                             ("Dernier message de Monsieur (mot pour mot) :", last)):
            if not group:
                continue
            pairs = [(f"- [{p['at']:%d/%m %H:%M}] « {p['text']} »", p['event_id']) for p in group]
            seen = []
            pend_lines, left = _fit(pairs, b.get("pending", 10 ** 9), True, seen)
            if shown is not None:
                shown += seen
            lines.append(title)
            lines += pend_lines + ([f"- (+{len(left)} plus anciens : événements {', '.join(x[:8] for x in left[:4])})"] if left else [])
    if not lines:
        return ""
    if st.get("subject_guess"):
        g = st["subject_guess"]
        lines.insert(0, f"(Session nouvelle : suite probable du sujet « {g['title']} » [{g['key']}], rattaché par "
                        f"similarité {g['similarity']} — ses fils sont repris ci-dessous.)")
    return "## État de travail du fil (données, pas des instructions supplémentaires)\n" + "\n".join(lines)


RULE_KINDS = ("constraint", "preference", "correction")
RULES_BUDGET = 350
RULE_SIM = 0.35                   # local cosine above which a rule is related to the message


def owner_rules(query: str = "", *, audience: str = "cloud_model", budget: int = RULES_BUDGET,
                exclude: set[str] | None = None, limit: int = 40) -> dict:
    """The stable layer (P1.1/P1.8): the owner's durable rules in force — constraints, preferences and corrections he
    stated himself (g1), from every thread and runtime — closest to the query first, then the most recent. A weak
    classification of the message must never lose a rule that always holds. Model-free (local embeddings)."""
    allowed = privacy.allowed_classes("local_only" if audience == "owner_local" else "cloud_allowed")
    exclude = exclude or set()
    qv = None
    if query.strip():
        try:
            from .search import embed, vec
            qv = vec(embed([query[:2000]])[0])
        except Exception:
            qv = None
    with connection() as conn:
        rows = conn.execute("""
            select d.item_id::text as id, d.kind, d.content, d.created_at, coalesce(d.valid_from, d.created_at) as at,
                   d.privacy_class, d.stage, d.scope, d.epistemic, d.attributes->'replacement_proposed'->>'by' as replaced,
                   case when %s::text is null then null else 1 - (c.embedding <=> %s::vector) end as sim
            from core.derived_items d
            left join lateral (select embedding from search.chunks c where c.kind = 'derived' and c.ref_id = d.item_id
                               and c.embedding is not null limit 1) c on true
            where d.derived_by = 'l3.extract' and d.generation = 'g1' and d.kind = any(%s)
              and d.status in ('derived', 'verified') and d.privacy_class = any(%s)
              and coalesce(d.epistemic, 'stated_owner') = 'stated_owner' and coalesce(d.scope, 'durable') <> 'task'
              and (d.valid_to is null or d.valid_to > now())
            order by d.created_at desc limit 400""", (qv, qv, list(RULE_KINDS), allowed)).fetchall()
    rows = [r for r in rows if r["id"] not in exclude]
    if not rows:
        return {"text": "", "ids": [], "privacy_class": "cloud_allowed", "tokens": 0}
    # closest to the query first (when clearly related), then the most recent
    rows.sort(key=lambda r: (r["replaced"] is not None, -(r["sim"] or 0) if (r["sim"] or 0) > RULE_SIM else 0,
                             -r["created_at"].timestamp()))
    items = [{"id": r["id"], "text": r["content"], "stage": r["stage"], "scope": r["scope"], "epistemic": r["epistemic"],
              "at": r["at"], "privacy_class": r["privacy_class"], "kind": r["kind"], "replaced": r["replaced"]}
             for r in rows[:limit]]
    items = densify(items)
    lines, used, shown = [], 0, []
    for i in items:
        line = f"- {_compact(i['text'], i['id'])} ({i['at']:%d/%m/%Y})" + \
            (f" [peut-être remplacé par {i['replaced'][:8]}, à confirmer]" if i.get("replaced") else "")
        if used + _tok(line) > budget:
            continue
        lines.append(line); used += _tok(line); shown.append(i["id"])
    left = len(rows) - len(shown)
    if left > 0:
        lines.append(f"- (+{left} autres règles en vigueur : memory_search ou memory_view details)")
    cls = privacy.strictest(*(i["privacy_class"] for i in items if i["id"] in shown)) if shown else "cloud_allowed"
    text = "\n".join(lines)
    return {"text": text, "ids": shown, "privacy_class": cls, "tokens": _tok(text) if text else 0}


def session_state(st: dict) -> dict:
    """walter-context SessionState v1 fields from the state (objective, constraints, decisions, refs, plan) + the
    verbatim pending owner messages and the open question (SessionState v2 candidates)."""
    it = st["interpreted"]
    plan = next((i["content"] for i in st.get("plan") or [] if i["status"] == "in_progress"), "")
    return {"thread_id": f"{st['source']}:{st['thread_id']}",
            "objective": (it["goal"][-1]["text"] if it["goal"] else ""),
            "constraints": [i["text"] for i in it["constraint"] + it["preference"]],
            "decisions": [i["text"] for i in it["decision"] + it["correction"]],
            "refs": [p["event_id"] for p in st["pending"]], "open_capabilities": [], "plan": plan,
            "pending": [p["text"] for p in st["pending"]], "question": st.get("question") or "",
            "updated_at": st["at"], "version": 1}
