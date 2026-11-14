"""Episodes of runs (P4, 2026-10-28): what a significant run did, how well, and what corrected it.

An episode is built from the run's own records — the run, its tasks, its model calls, its observations, the final
answer in walter_logs, its parent and children runs — never from memory of the conversation. The evaluation is
deterministic and separates three things (Monsieur, 2026-10-27):
  technical     did the tools and agents work (tasks failed, model attempts failed)
  functional    was the requested output delivered (output contract filled, observations stored)
  satisfaction  only what the owner said: corrected (a correction run exists), confirmed/refused (explicit feedback,
                later); silence stays `unknown`
The summary is written by the Router's `summarization` poste from that material only (no hardcoded model); a
local_only run gets no model call. A run that gets a correction or continuation re-versions its episode.
Trivial runs (no delegation, no model call through Walter, no observation, no tool work, not failed) get no episode.

A4 (socle 2026-11-11): execution experience is a memory. Every significant run gets an episode, failed, cancelled and
degraded ones included (until then a run that failed before any model call through Walter — 3 of 3 failed runs on
11-10/11 — was "trivial", and `pending()` only looked at runs with tasks or model calls). The material gains the run's
tool activity from walter_logs (names, error flags, masked excerpts), the run's structured `outcome` and the model-call
failures; the episode gains `outcome` = {status, errors, lessons, solutions, pending}: deterministic part from those
traces first, the lists completed by the summarization poste in the same call as the summary, strictly from the
material. The experience is then published as a g1 derived item (kind `experience`) and the run's objective (A3) is
updated through runs.task_update. `experience()` serves it back (gateway /v1/experience, Context layer).
"""
from __future__ import annotations

import json

from . import privacy
from .db import connect

PROMPT = ("Tu écris l'épisode d'une exécution de W.Alter, en français, à partir du seul JSON fourni : la demande, ce "
          "qui a été délégué et à quel modèle, les outils utilisés et leurs erreurs, ce qui a été obtenu (offres, "
          "sources), les observations réutilisées, les échecs et contournements, les corrections éventuelles de "
          "Monsieur. Reprends les valeurs telles qu'elles figurent dans le JSON : ne calcule rien, ne compare rien. "
          "Réponds par UN SEUL objet JSON, sans markdown, de la forme "
          '{"summary": "3 à 6 phrases factuelles", "status": "achieved|partial|failed|blocked|unknown", '
          '"errors": [{"what": "ce qui a échoué", "why": "pourquoi, selon les traces"}], '
          '"lessons": ["ce qu\'il faut retenir pour la prochaine fois"], "solutions": ["ce qui a fonctionné ou '
          'contourné un échec"], "pending": ["ce qui reste à faire"]}. '
          "Strictement depuis le matériel fourni : pas d'invention ; une liste vide quand le matériel n'en montre "
          "aucun ; status achieved seulement si la réponse finale montre la demande satisfaite, unknown si on ne "
          "peut pas le dire.")
TOOLS_SIGNIFICANT = 5          # tool calls from which a run with no delegation nor Walter model call has an episode
TOOL_EXCERPT = 240             # chars of a failed tool result kept (masked)
LIST_MAX, ITEM_CHARS = 5, 300  # outcome lists: items per list, chars per item
EPISODE_STATUSES = ("achieved", "partial", "failed", "blocked", "unknown")
EXPERIENCE_BY = "runs.episodes"


def _material(conn, run_id: str) -> dict | None:
    run = conn.execute("select * from runs.runs where run_id = %s", (run_id,)).fetchone()
    if not run:
        return None
    tasks = conn.execute("""select task_id, kind, goal, status, routing, result, session_id from runs.tasks
                            where run_id = %s order by started_at""", (run_id,)).fetchall()
    calls = conn.execute("""select count(*) n, count(*) filter (where not ok) failed, coalesce(sum(cost_usd), 0) cost,
                                   coalesce(sum(seconds), 0) seconds from models.exec_log where run_id = %s""",
                         (run_id,)).fetchone()
    obs = conn.execute("""select attributes->>'subject' subject, attributes->>'seller' seller, attributes->'values' vals,
                                 attributes->>'method' method from core.derived_items
                          where kind = 'sourced_observation' and attributes->>'run_id' = %s""", (run_id,)).fetchall()
    reused = conn.execute("""select d.attributes->>'subject' subject, d.attributes->>'seller' seller, d.attributes->'values' vals,
                                    d.attributes->>'method' method from runs.links l
                             join core.derived_items d on d.item_id::text = l.ref
                             where l.run_id = %s and l.kind = 'observation_reused'""", (run_id,)).fetchall()
    children = conn.execute("""select run_id, act, goal, status, correction from runs.runs where parent_run_id = %s
                               order by started_at""", (run_id,)).fetchall()
    answer = None
    sid = (run["origin"] or {}).get("session_id")
    if sid and privacy.cloud_readable(run["privacy_class"]):
        row = conn.execute("""select text from walter_logs.events where session_id = %s and type = 'assistant/message'
                              and occurred_at >= %s and occurred_at <= coalesce(%s, now()) + interval '2 minutes'
                              and privacy_class = any(%s) order by seq desc limit 1""",
                           (sid, run["started_at"], run["ended_at"], privacy.allowed_classes("cloud_allowed"))).fetchone()
        answer = (row["text"] or "")[:2500] if row else None
    model_failures = conn.execute("""select task, model_id, provider, skipped from models.exec_log
                                     where run_id = %s and not ok order by at limit 5""", (run_id,)).fetchall()
    return {"run": run, "tasks": tasks, "calls": calls, "observations": obs, "reused": reused, "children": children,
            "answer": answer, "tools": _tools(conn, run), "model_failures": model_failures}


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _tools(conn, run: dict) -> dict:
    """The run's tool activity in walter_logs (its harness session and that session's sub-agent sessions, in the run's
    window): calls, errors, distinct failing tools, a few masked excerpts of the failures (cloud-readable rows only)."""
    out = {"calls": 0, "errors": 0, "failing": [], "failures": [], "by_tool": {}}
    sid = (run["origin"] or {}).get("session_id")
    if not sid:
        return out
    rows = conn.execute("""select type, tool, call_id, status, left(text, 2000) as text, privacy_class from walter_logs.events
                           where (session_id = %s or session_id like %s) and type in ('tool/call', 'tool/result')
                             and occurred_at >= %s and occurred_at <= coalesce(%s, now()) + interval '2 minutes'
                           order by occurred_at, seq limit 3000""",
                        (sid, _like(sid) + ":%", run["started_at"], run["ended_at"])).fetchall()
    from .logs import mask
    names, readable = {}, privacy.allowed_classes("cloud_allowed")
    for r in rows:
        if r["type"] == "tool/call":
            out["calls"] += 1
            names[r["call_id"]] = r["tool"]
            out["by_tool"][r["tool"] or "?"] = out["by_tool"].get(r["tool"] or "?", 0) + 1
        elif r["status"] == "error":
            out["errors"] += 1
            tool = r["tool"] or names.get(r["call_id"]) or "?"
            if tool not in out["failing"]:
                out["failing"].append(tool)
            if len(out["failures"]) < LIST_MAX:
                text = " ".join((r["text"] or "").split())
                out["failures"].append({"tool": tool, "excerpt": mask(text)[:TOOL_EXCERPT]
                                        if r["privacy_class"] in readable and text else None})
    out["by_tool"] = dict(sorted(out["by_tool"].items(), key=lambda kv: -kv[1])[:12])
    return out


def evaluate(m: dict) -> dict:
    tasks, calls, run = m["tasks"], m["calls"], m["run"]
    failed = [t for t in tasks if t["status"] in ("failed", "abandoned")]
    contracts = [t for t in tasks if (t["routing"] or {}) and ((t.get("result") or {}).get("persisted") is not None)]
    stored = sum(((t.get("result") or {}).get("persisted") or {}).get("stored") or 0 for t in tasks)
    if not tasks:
        functional = {"contract": "unknown", "observations": len(m["observations"])}
    elif contracts:
        functional = {"contract": "filled" if stored else "reused" if m["reused"] else "empty",
                      "observations": len(m["observations"]), "reused": len(m["reused"])}
    else:
        functional = {"contract": "absent", "observations": len(m["observations"]), "reused": len(m["reused"])}
    tools = m.get("tools") or {"calls": 0, "errors": 0, "failing": []}
    ro = run.get("outcome") or {}
    degraded = bool(((run.get("routing") or {}).get("requested") or {}).get("degraded"))
    technical = {"status": "failed" if run["status"] == "failed" or ro.get("status") == "failed"
                 or (tasks and len(failed) == len(tasks))
                 else "degraded" if failed or calls["failed"] or tools["errors"] or degraded else "ok",
                 "tasks": len(tasks), "tasks_failed": len(failed), "model_calls": calls["n"],
                 "model_failures": calls["failed"],
                 "tools": {"calls": tools["calls"], "errors": tools["errors"], "failing": tools["failing"][:10]}}
    if degraded:
        technical["plan_degraded"] = True
    corrected = any(c["act"] == "correct" for c in m["children"])
    seconds = (run["ended_at"] - run["started_at"]).total_seconds() if run["ended_at"] else None
    return {"technical": technical, "functional": functional,
            "satisfaction": "corrected" if corrected else "unknown",
            "cost_usd": float(calls["cost"] or 0), "seconds": round(seconds, 1) if seconds else None}


def significant(m: dict) -> bool:
    """Worth an episode: delegation, a model call through Walter, observations, a failure (run failed, a structured
    outcome with an error, a degraded plan), or real tool work. A sub-agent run of a harness (channel machine) shares
    its session's journal with its parent: its tool activity counts for the parent, not for it."""
    run = m["run"]
    if m["tasks"] or m["calls"]["n"] or m["observations"] or m["reused"]:
        return True
    from .runs import has_tasks_schema
    if not has_tasks_schema():          # before migration 037: the previous rule (no new model calls, no new columns)
        return False
    ro = run.get("outcome") or {}
    if run["status"] == "failed" or ro.get("error") or ro.get("status") in ("failed", "interrupted"):
        return True
    if ((run.get("routing") or {}).get("requested") or {}).get("degraded"):
        return True
    if (run["origin"] or {}).get("channel") == "machine":
        return False
    tools = m.get("tools") or {}
    return bool(tools.get("errors")) or (tools.get("calls") or 0) >= TOOLS_SIGNIFICANT


def _facts(m: dict) -> dict:
    run = m["run"]
    return {"goal": run["goal"], "act": run["act"], "parent_run_id": str(run["parent_run_id"]) if run["parent_run_id"] else None,
            "correction": run["correction"],
            "tasks": [{"goal": (t["goal"] or "")[:300], "status": t["status"],
                       "model": (t["routing"] or {}).get("model_id"), "result": t["result"]} for t in m["tasks"]],
            "observations": [{"subject": o["subject"], "seller": o["seller"], "values": o["vals"], "method": o["method"]}
                             for o in m["observations"][:30]],
            "observations_reused": [{"subject": o["subject"], "seller": o["seller"], "values": o["vals"],
                                     "method": o["method"]} for o in m["reused"][:30]],
            "children": [{"run_id": str(c["run_id"]), "act": c["act"], "goal": c["goal"], "correction": c["correction"]}
                         for c in m["children"]],
            "run_status": run["status"], "run_outcome": run.get("outcome"),
            "tools": {k: (m.get("tools") or {}).get(k) for k in ("calls", "errors", "failing", "failures", "by_tool")},
            "model_failures": [{"task": x["task"], "model": x["model_id"], "provider": x["provider"],
                                "skipped": x["skipped"]} for x in m.get("model_failures") or []],
            "final_answer": m["answer"]}


def deterministic_outcome(m: dict, evaluation: dict) -> dict:
    """The outcome the traces alone establish (no model): errors from the run's outcome, failed tools, failed model
    calls and failed sub-tasks; status failed for a failed run, else unknown (only the material read by the model —
    or the owner — can say achieved / partial)."""
    run, errors = m["run"], []
    ro = run.get("outcome") or {}
    if ro.get("error"):
        kind = ro["error"].get("kind") or "erreur d'exécution"
        what = {"engine_restart": "interrompu par un redémarrage du moteur",
                "budget": "arrêté au plafond du tour (budget)"}.get(kind, kind)
        errors.append({"what": what, "why": ro["error"].get("message") or ""})
    for f in (m.get("tools") or {}).get("failures") or []:
        errors.append({"what": f"outil {f['tool']}", "why": f.get("excerpt") or "erreur signalée par l'outil"})
    for x in m.get("model_failures") or []:
        errors.append({"what": f"appel modèle {x['task'] or ''} ({x['model_id'] or '?'})".replace("  ", " "),
                       "why": x["skipped"] or "échec de l'appel"})
    for t in m["tasks"]:
        if t["status"] in ("failed", "abandoned"):
            errors.append({"what": f"sous-tâche {t['kind']}",
                           "why": str((t["result"] or {}).get("error") or t["status"])[:ITEM_CHARS]})
    failed = run["status"] == "failed" or ro.get("status") == "failed" or evaluation["technical"]["status"] == "failed"
    return {"status": "failed" if failed else "unknown", "errors": _dedupe(errors)[:8], "lessons": [], "solutions": [],
            "pending": []}


def _dedupe(errors: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in errors:
        key = (str(e.get("what"))[:80], str(e.get("why"))[:80])
        if key not in seen:
            seen.add(key); out.append(e)
    return out


def _strings(v) -> list[str]:
    from .logs import mask
    if not isinstance(v, list):
        return []
    return [mask(" ".join(str(x).split()))[:ITEM_CHARS] for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:LIST_MAX]


def parse_model(content: str | None) -> dict | None:
    """The summarising model's single JSON object, parsed defensively (fences, prose around it). None when absent."""
    if not content:
        return None
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def merge_outcome(det: dict, model: dict | None, run_status: str, interrupted: bool = False) -> dict:
    """Deterministic outcome first; the model adds lists and may say achieved / partial — never achieved for a run that
    failed or was interrupted, and never something other than failed / blocked / partial for a failed run."""
    if not model:
        return det
    from .logs import mask
    status = model.get("status") if model.get("status") in EPISODE_STATUSES else det["status"]
    if run_status in ("failed",) or det["status"] == "failed":
        status = status if status in ("failed", "blocked", "partial") else "failed"
    elif (run_status in ("cancelled", "abandoned") or interrupted) and status == "achieved":
        status = "partial"
    extra = [{"what": mask(str(e.get("what") or ""))[:ITEM_CHARS], "why": mask(str(e.get("why") or ""))[:ITEM_CHARS]}
             for e in (model.get("errors") or []) if isinstance(e, dict) and (e.get("what") or e.get("why"))]
    return {"status": status, "errors": _dedupe(det["errors"] + extra)[:8], "lessons": _strings(model.get("lessons")),
            "solutions": _strings(model.get("solutions")), "pending": _strings(model.get("pending"))}


def build(run_id: str, *, reason: str = "run_ended", summarise: bool = True) -> dict:
    with connect() as conn:
        m = _material(conn, run_id)
        if not m:
            return {"error": "unknown run"}
        if m["run"]["status"] == "open":
            return {"skipped": "run still open"}
        if not significant(m):
            # remembered as looked at, so the catch-up (pending) does not pick the same trivial runs again and again
            conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'episode', 'trivial') on conflict do nothing",
                         (run_id,))
            parent = m["run"]["parent_run_id"]
            out = {"skipped": "trivial run"}
            if parent and reason == "run_ended":         # a short correction still re-versions what it corrects
                out["parent"] = build(str(parent), reason="child_run", summarise=summarise)
            return out
        evaluation, facts = evaluate(m), _facts(m)
        version = conn.execute("select coalesce(max(version), 0) + 1 v from runs.episodes where run_id = %s",
                               (run_id,)).fetchone()["v"]
    det = deterministic_outcome(m, evaluation)
    summary = model = parsed = None
    from . import organic
    if summarise and not organic.extraction_paused() and privacy.cloud_readable(m["run"]["privacy_class"]):
        from . import llm
        try:
            r = llm.chat([{"role": "system", "content": PROMPT},
                          {"role": "user", "content": json.dumps({"facts": facts, "evaluation": evaluation,
                                                                  "deterministic_outcome": det},
                                                                 ensure_ascii=False, default=str)[:14000]}],
                         poste="summarization", processor="episodes", privacy_class=m["run"]["privacy_class"],
                         budget="recurring", purpose="run episode", timeout=90)
            content, model = (r.get("content") or "").strip() or None, r.get("model")
            parsed = parse_model(content)
            summary = (str(parsed.get("summary") or "").strip() or None) if parsed else content
        except Exception:  # noqa: BLE001 — the episode keeps its deterministic part
            summary = None
    ro = m["run"].get("outcome") or {}
    outcome = merge_outcome(det, parsed, m["run"]["status"],
                            interrupted=ro.get("status") in ("interrupted", "cancelled")
                            or (ro.get("error") or {}).get("kind") == "engine_restart")
    from .runs import has_tasks_schema
    migrated = has_tasks_schema()
    with connect() as conn:
        if migrated:
            conn.execute("""insert into runs.episodes (run_id, version, summary, evaluation, facts, model, reason, outcome)
                            values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
                         (run_id, version, summary, json.dumps(evaluation), json.dumps(facts, default=str), model,
                          reason, json.dumps(outcome, ensure_ascii=False)))
        else:                               # before migration 037 (no outcome column): the episode as before
            conn.execute("""insert into runs.episodes (run_id, version, summary, evaluation, facts, model, reason)
                            values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
                         (run_id, version, summary, json.dumps(evaluation), json.dumps(facts, default=str), model,
                          reason))
        conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'episode', %s) on conflict do nothing",
                     (run_id, f"{run_id}:v{version}"))
        conn.execute("""insert into bus.events (type, source, subject, payload) values ('episode.written', 'runs', %s, %s)""",
                     (run_id, json.dumps({"run_id": run_id, "version": version, "reason": reason,
                                          "status": outcome["status"]})))
    out = {"run_id": run_id, "version": version, "evaluation": evaluation, "summary": summary, "outcome": outcome}
    if not migrated:
        parent = facts["parent_run_id"]
        if parent and reason == "run_ended":
            out["parent"] = build(parent, reason="child_run", summarise=summarise)
        return out
    try:
        out["experience"] = publish_experience(m["run"], version, summary, outcome)
    except Exception as e:  # noqa: BLE001 — the episode stands; the catch-up republishes
        out["experience"] = {"error": type(e).__name__}
    try:
        out["task"] = update_objective(m["run"], outcome, summary)
    except Exception as e:  # noqa: BLE001
        out["task"] = {"error": type(e).__name__}
    parent = facts["parent_run_id"]
    if parent and reason == "run_ended":                 # a correction or continuation re-versions the parent
        out["parent"] = build(parent, reason="child_run", summarise=summarise)
    return out


STATUS_FR = {"achieved": "réussie", "partial": "partielle", "failed": "échouée", "blocked": "bloquée",
             "unknown": "issue non établie"}


def worth_publishing(outcome: dict) -> bool:
    """An experience enters the searchable memory when it teaches something: errors, lessons, solutions, what is
    left, or an outcome other than achieved / unknown. A plain success stays in runs.episodes (experience() reads it)."""
    return bool(outcome["errors"] or outcome["lessons"] or outcome["solutions"] or outcome["pending"]
                or outcome["status"] in ("failed", "partial", "blocked"))


def experience_text(run: dict, summary: str | None, outcome: dict) -> str:
    at = run["ended_at"] or run["started_at"]
    parts = [f"Expérience d'exécution du {at:%d/%m/%Y %H:%M} ({STATUS_FR.get(outcome['status'], outcome['status'])})"
             + (f" — demande : {' '.join(run['goal'].split())[:200]}" if run.get("goal") else "") + "."]
    if summary:
        parts.append(summary.strip())
    if outcome["errors"]:
        parts.append("Erreurs : " + " ; ".join(f"{e['what']} ({e['why']})" if e.get("why") else e["what"]
                                               for e in outcome["errors"][:5]) + ".")
    for key, title in (("lessons", "Leçons"), ("solutions", "Solutions"), ("pending", "Reste à faire")):
        if outcome[key]:
            parts.append(f"{title} : " + " ; ".join(outcome[key]) + ".")
    return "\n".join(parts)


def _owner_event(conn, run: dict) -> list[str]:
    """The owner message that opened the run (provenance of the experience item; without one the item stays out of
    cloud search results, experience() still serves it)."""
    origin = run["origin"] or {}
    sid, rt = origin.get("session_id") or "", origin.get("runtime")
    native = sid.rsplit("/", 1)[-1]
    if not native or not rt:
        return []
    row = conn.execute("""select event_id::text from core.events where source = %s and thread_id = %s
                          and event_type = 'message.sent'
                          and occurred_at between %s - interval '2 minutes' and %s + interval '2 minutes'
                          order by abs(extract(epoch from occurred_at - %s)) limit 1""",
                       (rt, native, run["started_at"], run["started_at"], run["started_at"])).fetchone()
    return [row["event_id"]] if row else []


def publish_experience(run: dict, version: int, summary: str | None, outcome: dict) -> dict:
    """The episode as a g1 derived item kind `experience` (epistemic agent_reported, stage executed), linked to the
    run (source_refs.ref / attributes.run_id), its thread and its objective; idempotent per run+version, a new version
    supersedes the previous one (same lineage). Indexed for search like any derived item."""
    run_id = str(run["run_id"])
    ref = f"experience:{run_id}:v{version}"
    from . import runs as _runs
    task_id = _runs.objective_of_run(run_id)
    with connect() as conn:
        prev = conn.execute("""select item_id::text, lineage_id::text from core.derived_items where derived_by = %s
                               and kind = 'experience' and attributes->>'run_id' = %s and status in ('derived', 'verified')
                               and source_refs->>'ref' <> %s order by created_at desc""",
                            (EXPERIENCE_BY, run_id, ref)).fetchall()
        if not worth_publishing(outcome):
            for p in prev:
                conn.execute("""update core.derived_items set status = 'superseded', valid_to = now(),
                                attributes = attributes || jsonb_build_object('superseded_reason', 'later episode: nothing to learn')
                                where item_id = %s""", (p["item_id"],))
            return {"published": False, "superseded": len(prev)}
        origin = run["origin"] or {}
        attrs = {"run_id": run_id, "version": version, "thread_id": run["thread_id"], "task_id": task_id,
                 "status": outcome["status"], "errors": outcome["errors"], "lessons": outcome["lessons"],
                 "solutions": outcome["solutions"], "pending": outcome["pending"], "summary": summary}
        row = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                                  source_event_ids, source_refs, valid_from, confidence, privacy_class, generation,
                                  epistemic, stage, scope, lineage_id)
                              values ('experience', %s, %s, 'derived', %s, '1', %s::uuid[], %s, %s, 1.0, %s, 'g1',
                                      'agent_reported', 'executed', 'durable', %s::uuid)
                              on conflict (derived_by, (source_refs->>'ref')) where source_refs ? 'ref' do nothing
                              returning item_id::text""",
                           (experience_text(run, summary, outcome), json.dumps(attrs, ensure_ascii=False, default=str),
                            EXPERIENCE_BY, _owner_event(conn, run),
                            json.dumps({"ref": ref, "run_id": run_id, "thread": run["thread_id"],
                                        "source": origin.get("runtime"), "session_id": origin.get("session_id")}),
                            run["ended_at"] or run["started_at"], run["privacy_class"],
                            prev[0]["lineage_id"] if prev else None)).fetchone()
        if not row:
            return {"published": False, "duplicate": True}
        for p in prev:
            conn.execute("""update core.derived_items set status = 'superseded', valid_to = now(),
                            attributes = attributes || jsonb_build_object('superseded_by', %s::text)
                            where item_id = %s""", (row["item_id"], p["item_id"]))
    return {"published": True, "item_id": row["item_id"], "superseded": len(prev)}


def update_objective(run: dict, outcome: dict, summary: str | None) -> dict | None:
    """The run's objective (A3) after its evaluation: done when achieved with nothing pending; suspended (resumable)
    when the run was interrupted (outcome.status interrupted, error.kind engine_restart); a failure — a budget stop
    (error.kind budget) included — keeps it open, a retry being plausible (only the owner or the engine's task_state
    sets failed / cancelled); otherwise it stays open with what is pending. last_outcome is recorded."""
    from . import runs as _runs
    run_id = str(run["run_id"])
    task_id = _runs.objective_of_run(run_id)
    if not task_id:
        return None
    cur = _runs.task_get(task_id)
    if not cur or cur["status"] in ("cancelled",):
        return {"task_id": task_id, "unchanged": True}
    with connect() as conn:            # an older attempt re-versioned later (a child run arrived) never rewinds it
        later = conn.execute("""select 1 from runs.task_runs tr join runs.runs r on r.run_id = tr.run_id
                                where tr.task_id = %s and r.started_at > %s limit 1""",
                             (task_id, run["started_at"])).fetchone()
    if later:
        return {"task_id": task_id, "unchanged": True, "reason": "a later attempt exists"}
    st = outcome["status"]
    reason = (outcome["errors"][0]["what"] + (f" — {outcome['errors'][0]['why']}" if outcome["errors"][0].get("why") else "")
              if outcome["errors"] else (outcome["pending"][0] if outcome["pending"] else None))
    last = {"status": st, "reason": reason[:160] if reason else None, "run_id": run_id,
            "at": (run["ended_at"] or run["started_at"]).isoformat()}
    ro = run.get("outcome") or {}
    interrupted = ro.get("status") == "interrupted" or (ro.get("error") or {}).get("kind") == "engine_restart"
    status = None
    if st == "achieved" and not outcome["pending"] and not interrupted:
        status = "done"
    elif interrupted:
        status = "suspended"          # interrupted (engine restart…): resumable, the next continuation re-opens it
    elif cur["status"] == "suspended":
        status = "open"
    progress = {}
    if outcome["pending"]:
        progress["pending"] = outcome["pending"]
    if outcome["solutions"]:
        progress["done"] = (list((cur["progress"] or {}).get("done") or []) + outcome["solutions"])[-10:]
    result = None
    if status == "done":
        result = {"summary": summary, "refs": {"runs": [run_id]}}
    res = _runs.task_update(task_id, status=status, progress=progress or None, result=result, last_outcome=last,
                            by="episode")
    return {"task_id": task_id, "status": res.get("status")}


def pending(hours: int = 48, limit: int = 20) -> list[dict]:
    """Ended runs of the last hours never looked at (no episode, no trivial mark): catch-up when a detached build was
    lost. Failed / cancelled runs included (A4); build() decides what is significant and marks the rest."""
    from .runs import has_tasks_schema
    if not has_tasks_schema():          # before migration 037: the previous selection
        with connect() as conn:
            ids = [str(r["run_id"]) for r in conn.execute(
                """select r.run_id from runs.runs r where r.status <> 'open' and r.ended_at > now() - make_interval(hours => %s)
                   and not exists (select 1 from runs.episodes e where e.run_id = r.run_id)
                   and (exists (select 1 from runs.tasks t where t.run_id = r.run_id)
                        or exists (select 1 from models.exec_log x where x.run_id = r.run_id))
                   order by r.ended_at limit %s""", (hours, limit))]
        return [build(i) for i in ids]
    with connect() as conn:
        ids = [str(r["run_id"]) for r in conn.execute(
            """select r.run_id from runs.runs r where r.status <> 'open' and r.ended_at > now() - make_interval(hours => %s)
               and not exists (select 1 from runs.episodes e where e.run_id = r.run_id)
               and not exists (select 1 from runs.links l where l.run_id = r.run_id and l.kind = 'episode')
               order by (r.status = 'failed') desc, r.ended_at limit %s""", (hours, limit))]
    return [build(i) for i in ids]


def experience(thread_id: str | None = None, query: str | None = None, limit: int = 5,
               max_privacy: str = "cloud_allowed") -> list[dict]:
    """What was already tried (A4), binding shape {at, run_id, status, summary, errors, lessons, solutions, pending}:
    the latest episode version per run of the thread, failures and partial outcomes first, then the most recent; with
    `query`, also the best matches among other threads' published experience (search over kind experience)."""
    limit = max(1, min(int(limit or 5), 20))
    from .runs import has_tasks_schema
    if not has_tasks_schema():          # no episode outcome before migration 037
        return []
    allowed = privacy.allowed_classes(max_privacy)
    items: list[dict] = []
    seen: set[str] = set()
    if thread_id:
        with connect() as conn:
            rows = conn.execute("""
                select distinct on (e.run_id) e.run_id::text, e.version, e.summary, e.outcome, e.evaluation,
                       coalesce(r.ended_at, e.created_at) at, r.status run_status, r.goal
                from runs.episodes e join runs.runs r on r.run_id = e.run_id
                where r.thread_id = %s and r.privacy_class = any(%s)
                order by e.run_id, e.version desc""", (thread_id, allowed)).fetchall()
        rank = {"failed": 0, "blocked": 0, "partial": 1}
        rows = sorted(rows, key=lambda r: (rank.get(((r["outcome"] or {}).get("status")), 2), -r["at"].timestamp()))
        for r in rows[:limit]:
            items.append(_exp_shape(r)); seen.add(r["run_id"])
    if query and query.strip() and len(items) < limit:
        try:
            from . import search
            hits = search.search(query, limit=limit * 2, labels=["experience"], lanes=("knowledge",),
                                 max_privacy=max_privacy)
        except Exception:  # noqa: BLE001 — search is a bonus here
            hits = []
        ids = [str(h["ref_id"]) for h in hits]
        if ids:
            with connect() as conn:
                found = conn.execute("""select d.attributes->>'run_id' run_id from core.derived_items d
                                        where d.item_id::text = any(%s) and d.status in ('derived', 'verified')""",
                                     (ids,)).fetchall()
                run_ids = [f["run_id"] for f in found if f["run_id"] and f["run_id"] not in seen]
                rows = conn.execute("""
                    select distinct on (e.run_id) e.run_id::text, e.version, e.summary, e.outcome, e.evaluation,
                           coalesce(r.ended_at, e.created_at) at, r.status run_status, r.goal, r.thread_id
                    from runs.episodes e join runs.runs r on r.run_id = e.run_id
                    where e.run_id::text = any(%s) and r.privacy_class = any(%s)
                    order by e.run_id, e.version desc""", (run_ids, allowed)).fetchall() if run_ids else []
            order = {rid: i for i, rid in enumerate(run_ids)}
            rows = _close_to(query, sorted(rows, key=lambda r: order.get(r["run_id"], 99)))
            for r in rows:
                if len(items) >= limit:
                    break
                items.append(_exp_shape(r) | {"thread_id": r["thread_id"], "other_thread": True})
    return items


EXPERIENCE_SIM = 0.55      # request ↔ past request similarity (local embeddings) under which another thread's
                           # experience is not served: search ranks, it does not say « this is about the same thing ».
                           # Measured 12/11: same request 0.82, paraphrase 0.69 ; other requests that only share a
                           # vocabulary 0.42–0.46 (they were served at 0.40), unrelated ≤ 0.20


def _close_to(query: str, rows: list[dict], embed=None) -> list[dict]:
    """Rows whose request (goal, else summary) is about what the query asks. Without embeddings: none (an experience
    served on the wrong subject misleads more than a missing one; the thread's own experience never passes here)."""
    if not rows:
        return []
    try:
        if embed is None:
            from .search import embed
        vs = embed([query[:1500]] + [(r.get("goal") or r.get("summary") or "")[:1500] for r in rows])
    except Exception:  # noqa: BLE001
        return []
    norm = lambda v: sum(x * x for x in v) ** 0.5 or 1.0                                  # noqa: E731
    q, qn = vs[0], norm(vs[0])
    return [r for r, v in zip(rows, vs[1:]) if sum(a * b for a, b in zip(q, v)) / (qn * norm(v)) >= EXPERIENCE_SIM]


def _exp_shape(r: dict) -> dict:
    o = r["outcome"] or {}
    status = o.get("status") or ("failed" if r["run_status"] == "failed" else "unknown")
    return {"at": r["at"].isoformat(), "run_id": r["run_id"], "status": status, "summary": r["summary"],
            "goal": r.get("goal"), "errors": o.get("errors") or [], "lessons": o.get("lessons") or [],
            "solutions": o.get("solutions") or [], "pending": o.get("pending") or []}


def latest(run_id: str) -> dict | None:
    with connect() as conn:
        return conn.execute("select * from runs.episodes where run_id = %s order by version desc limit 1",
                            (run_id,)).fetchone()
