"""L3 extraction (P5, A1): synthesis of W.Alter conversations into derived knowledge with exact provenance.

Per Hermes session segment → one `summary` derived item + `decision` / `preference` / `fact` / `open_loop` items,
each citing the message events it comes from. local_only messages never enter the prompt. Versioned (processor,
version, model, prompt hash) so the history can be re-processed later with a better model (§29–30).
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from . import llm
from .db import connection

PROCESSOR, VERSION = "l3.conversation_summary", "1"
MODEL = "google/gemini-3.6-flash"
SEGMENT_CHARS = 30000
PROMPT = """Tu analyses un extrait de conversation entre Monsieur (l'utilisateur) et son assistant personnel W.Alter.
Messages numérotés :
{transcript}

Outils utilisés pendant l'extrait : {tools}

Produis un JSON :
{{"summary": "3 à 6 phrases en français : de quoi il a été question, ce qui a été fait, où on en est",
  "topics": ["..."],
  "decisions": [{{"text": "décision prise par Monsieur (ou validée par lui) et sa raison si connue", "msgs": [n, ...]}}],
  "preferences": [{{"text": "préférence durable de Monsieur (goût, manière de travailler, règle pour W.Alter)", "msgs": [n]}}],
  "facts": [{{"text": "fait durable sur Monsieur, sa vie, ses projets ou ses proches (pas de détail technique interne)", "msgs": [n]}}],
  "open_loops": [{{"text": "chose promise, en attente ou à faire", "msgs": [n]}}],
  "people": ["personnes citées (hors Monsieur et W.Alter)"], "projects": ["projets cités"]}}
Règles : uniquement ce qui est explicitement dans les messages ; listes vides si rien ; pas de détails de configuration,
de ports, de commandes ou de bugs comme faits ; chaque élément cite ses numéros de messages."""
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:16]


def pending_sessions(limit: int, since=None) -> list[str]:
    with connection() as conn:
        return [r["thread_id"] for r in conn.execute("""
            select e.thread_id from core.events e
            where e.source = 'hermes' and e.event_type in ('message.sent','message.received')
              and (%s::timestamptz is null or e.occurred_at >= %s::timestamptz)
            group by e.thread_id
            having count(*) >= 2 and max(e.occurred_at) < now() - interval '30 minutes'
               and not exists (select 1 from core.derived_items d where d.derived_by = %s and d.processor_version = %s
                               and d.kind = 'summary' and d.source_refs->>'session' = e.thread_id)
            order by max(e.occurred_at) desc limit %s""", (since, since, PROCESSOR, VERSION, limit)).fetchall()]


def _segments(msgs: list[dict]) -> list[list[dict]]:
    segs, cur, size = [], [], 0
    for m in msgs:
        n = len(m["content"] or "")
        if cur and size + n > SEGMENT_CHARS:
            segs.append(cur); cur, size = [], 0
        cur.append(m); size += min(n, 4000)
    if cur:
        segs.append(cur)
    return segs


def summarize_session(session_id: str, budget: str = "recurring") -> dict:
    with connection() as conn:
        msgs = conn.execute("""select event_id, event_type, occurred_at, content, privacy_class from core.events
                               where source = 'hermes' and thread_id = %s and event_type in ('message.sent','message.received')
                               order by occurred_at""", (session_id,)).fetchall()
        tools = [r["tool"] for r in conn.execute("""select payload->>'tool' tool, count(*) from core.events
                    where source = 'hermes' and thread_id = %s and event_type = 'tool.called' group by 1 order by 2 desc limit 12""",
                                                 (session_id,)).fetchall()]
        title = conn.execute("""select content from core.events where source = 'hermes' and thread_id = %s
                                and event_type = 'conversation.started'""", (session_id,)).fetchone()
    usable = [m for m in msgs if m["privacy_class"] != "local_only"]
    out = {"segments": 0, "items": 0, "cost_usd": 0.0}
    for si, seg in enumerate(_segments(usable)):
        lines = [f"{i + 1}. [{'Monsieur' if m['event_type'] == 'message.sent' else 'W.Alter'} · {m['occurred_at']:%Y-%m-%d %H:%M}] "
                 f"{(m['content'] or '')[:4000]}" for i, m in enumerate(seg)]
        res = llm.chat([{"role": "user", "content": PROMPT.format(transcript="\n".join(lines), tools=", ".join(tools) or "aucun")}],
                       model=MODEL, processor=PROCESSOR, processor_version=VERSION, privacy_class="cloud_allowed",
                       budget=budget, purpose=f"session {session_id} segment {si}", response_format={"type": "json_object"},
                       reasoning={"effort": "low"}, max_tokens=6000)
        out["cost_usd"] += float(res["cost_usd"] or 0)
        c = res["content"]
        data = json.loads(c[c.find("{"):c.rfind("}") + 1])
        ids = [m["event_id"] for m in seg]

        def cite(nums):
            return [ids[n - 1] for n in nums or [] if isinstance(n, int) and 1 <= n <= len(ids)] or ids

        base = {"processor_version": VERSION, "model": MODEL, "prompt_hash": PROMPT_HASH, "status": "derived",
                "derived_by": PROCESSOR}
        rows = [{"kind": "summary", "content": data.get("summary") or "", "source_event_ids": ids,
                 "attributes": {"topics": data.get("topics") or [], "people": data.get("people") or [],
                                "projects": data.get("projects") or [], "tools": tools, "title": title["content"] if title else None,
                                "segment": si, "from": str(seg[0]["occurred_at"]), "to": str(seg[-1]["occurred_at"])},
                 "ref": f"{session_id}:{si}:summary"}]
        for kind, key in (("decision", "decisions"), ("preference", "preferences"), ("fact", "facts"), ("open_loop", "open_loops")):
            for k, item in enumerate(data.get(key) or []):
                if isinstance(item, dict) and item.get("text"):
                    rows.append({"kind": kind, "content": item["text"], "source_event_ids": cite(item.get("msgs")),
                                 "attributes": {"segment": si}, "ref": f"{session_id}:{si}:{kind}:{k}"})
        with connection() as conn:
            for r in rows:
                if not r["content"]:
                    continue
                conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                                    model, prompt_hash, source_event_ids, source_refs, valid_from, privacy_class)
                                values (%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s,'cloud_allowed')
                                on conflict (derived_by, (source_refs->>'ref')) where source_refs ? 'ref' do nothing""",
                             (r["kind"], r["content"], json.dumps(r["attributes"], ensure_ascii=False), base["status"],
                              base["derived_by"], VERSION, MODEL, PROMPT_HASH, r["source_event_ids"],
                              json.dumps({"ref": r["ref"], "session": session_id}), seg[-1]["occurred_at"]))
                out["items"] += 1
        out["segments"] += 1
    return out


def run(limit: int = 20, since=None, budget: str = "recurring", workers: int = 6) -> dict:
    import concurrent.futures as cf
    total = {"sessions": 0, "segments": 0, "items": 0, "cost_usd": 0.0, "errors": 0}

    def one(sid):
        try:
            return summarize_session(sid, budget)
        except llm.BudgetExceeded:
            return "budget"
        except Exception:
            return None
    with cf.ThreadPoolExecutor(workers) as ex:
        for r in ex.map(one, pending_sessions(limit, since)):
            if r == "budget":
                total["stopped"] = "budget exhausted"; continue
            if r is None:
                total["errors"] += 1; continue
            total["sessions"] += 1
            for k in ("segments", "items", "cost_usd"):
                total[k] += r[k]
    return total
