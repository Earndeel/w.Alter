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
Trivial runs (no delegation, no model call through Walter, no observation) get no episode.
"""
from __future__ import annotations

import json

from .db import connect

PROMPT = ("Tu écris l'épisode d'une exécution de W.Alter, en français, 3 à 6 phrases factuelles, à partir du seul JSON "
          "fourni : la demande, ce qui a été délégué et à quel modèle, ce qui a été obtenu (offres, sources), les "
          "observations réutilisées (déjà relevées par un run précédent), les échecs et contournements, les corrections "
          "éventuelles de Monsieur. Reprends les valeurs telles qu'elles "
          "figurent dans le JSON : ne calcule rien, ne compare rien, ne conclus pas à la place de l'exécution. "
          "Pas d'invention, pas de conseil, pas de markdown. Si une information manque, ne la mentionne pas.")


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
    if sid and run["privacy_class"] != "local_only":
        row = conn.execute("""select text from walter_logs.events where session_id = %s and type = 'assistant/message'
                              and occurred_at >= %s and occurred_at <= coalesce(%s, now()) + interval '2 minutes'
                              and privacy_class = 'cloud_allowed' order by seq desc limit 1""",
                           (sid, run["started_at"], run["ended_at"])).fetchone()
        answer = (row["text"] or "")[:2500] if row else None
    return {"run": run, "tasks": tasks, "calls": calls, "observations": obs, "reused": reused, "children": children,
            "answer": answer}


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
    technical = {"status": "failed" if run["status"] == "failed" or (tasks and len(failed) == len(tasks))
                 else "degraded" if failed or calls["failed"] else "ok",
                 "tasks": len(tasks), "tasks_failed": len(failed), "model_calls": calls["n"],
                 "model_failures": calls["failed"]}
    corrected = any(c["act"] == "correct" for c in m["children"])
    seconds = (run["ended_at"] - run["started_at"]).total_seconds() if run["ended_at"] else None
    return {"technical": technical, "functional": functional,
            "satisfaction": "corrected" if corrected else "unknown",
            "cost_usd": float(calls["cost"] or 0), "seconds": round(seconds, 1) if seconds else None}


def significant(m: dict) -> bool:
    return bool(m["tasks"] or m["calls"]["n"] or m["observations"] or m["reused"])


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
            "final_answer": m["answer"]}


def build(run_id: str, *, reason: str = "run_ended", summarise: bool = True) -> dict:
    with connect() as conn:
        m = _material(conn, run_id)
        if not m:
            return {"error": "unknown run"}
        if m["run"]["status"] == "open":
            return {"skipped": "run still open"}
        if not significant(m):
            parent = m["run"]["parent_run_id"]
            out = {"skipped": "trivial run"}
            if parent and reason == "run_ended":         # a short correction still re-versions what it corrects
                out["parent"] = build(str(parent), reason="child_run", summarise=summarise)
            return out
        evaluation, facts = evaluate(m), _facts(m)
        version = conn.execute("select coalesce(max(version), 0) + 1 v from runs.episodes where run_id = %s",
                               (run_id,)).fetchone()["v"]
    summary = model = None
    if summarise and m["run"]["privacy_class"] != "local_only":
        from . import llm
        try:
            r = llm.chat([{"role": "system", "content": PROMPT},
                          {"role": "user", "content": json.dumps({"facts": facts, "evaluation": evaluation},
                                                                 ensure_ascii=False, default=str)[:12000]}],
                         poste="summarization", processor="episodes", privacy_class=m["run"]["privacy_class"],
                         budget="recurring", purpose="run episode", timeout=90)
            summary, model = (r.get("content") or "").strip() or None, r.get("model")
        except Exception:  # noqa: BLE001 — the episode keeps its deterministic part
            summary = None
    with connect() as conn:
        conn.execute("""insert into runs.episodes (run_id, version, summary, evaluation, facts, model, reason)
                        values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
                     (run_id, version, summary, json.dumps(evaluation), json.dumps(facts, default=str), model, reason))
        conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'episode', %s) on conflict do nothing",
                     (run_id, f"{run_id}:v{version}"))
        conn.execute("""insert into bus.events (type, source, subject, payload) values ('episode.written', 'runs', %s, %s)""",
                     (run_id, json.dumps({"run_id": run_id, "version": version, "reason": reason})))
    out = {"run_id": run_id, "version": version, "evaluation": evaluation, "summary": summary}
    parent = facts["parent_run_id"]
    if parent and reason == "run_ended":                 # a correction or continuation re-versions the parent
        out["parent"] = build(parent, reason="child_run", summarise=summarise)
    return out


def pending(hours: int = 48, limit: int = 20) -> list[dict]:
    """Ended runs of the last hours without an episode (catch-up when a detached build was lost)."""
    with connect() as conn:
        ids = [str(r["run_id"]) for r in conn.execute(
            """select r.run_id from runs.runs r where r.status <> 'open' and r.ended_at > now() - make_interval(hours => %s)
               and not exists (select 1 from runs.episodes e where e.run_id = r.run_id)
               and (exists (select 1 from runs.tasks t where t.run_id = r.run_id)
                    or exists (select 1 from models.exec_log x where x.run_id = r.run_id))
               order by r.ended_at limit %s""", (hours, limit))]
    return [build(i) for i in ids]


def latest(run_id: str) -> dict | None:
    with connect() as conn:
        return conn.execute("select * from runs.episodes where run_id = %s order by version desc limit 1",
                            (run_id,)).fetchone()
