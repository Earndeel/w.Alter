"""Monsieur's model knowledge and the intent-aware decision built on it.

Leaderboards say which model is measured best; `config/knowledge.json` says what each model is *for*
(profiles), which objective calls for which favourite (roles + French request signals), what a model demands
before generating (workflow), how it is accessed (Flow credits, Codex subscription) and who wins a close call
(affinities). `decide()` turns a free-text request into a role, a model, a route and a plan, and returns a short
brief so the orchestrator can overrule the keyword match when the request is subtle.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from . import catalog, choose

KNOWLEDGE = Path(__file__).resolve().parent.parent / "config" / "knowledge.json"
TIE_MARGIN = {"AA Intelligence Index": 1.0, "Composite /100": 1.5}   # score points inside which two models are a tie
ELO_TIE = 10.0                                  # Elo boards (Arena, AA arenas, Design Arena)


def load() -> dict:
    return json.loads(KNOWLEDGE.read_text())


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " " + re.sub(r"[^a-z0-9]+", " ", text).strip() + " "


def hits(text: str, signals: list[str]) -> list[str]:
    t = norm(text)
    return [s for s in signals if norm(s) in t]


# --- declarations ---------------------------------------------------------------------------------------

def declare(conn, doc: dict | None = None) -> dict:
    """Apply knowledge.json: profiles, roles (favourites per objective), retired roles, affinities. Idempotent."""
    doc = doc or load()
    for model_id, p in doc["profiles"].items():
        conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (model_id,))
        conn.execute("""insert into models.profiles (model_id, strengths, weaknesses, workflow, effort, access_note,
                          cost_note, content_policy, note, declared_at)
                        values (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
                        on conflict (model_id) do update set strengths = excluded.strengths,
                          weaknesses = excluded.weaknesses, workflow = excluded.workflow, effort = excluded.effort,
                          access_note = excluded.access_note, cost_note = excluded.cost_note,
                          content_policy = excluded.content_policy, note = excluded.note,
                          declared_at = excluded.declared_at""",
                     (model_id, p.get("strengths", []), p.get("weaknesses", []), json.dumps(p.get("workflow", [])),
                      p.get("effort"), p.get("access_note"), p.get("cost_note"), p.get("content_policy"),
                      p.get("note"), p.get("declared_at")))
    roles = {k: v for k, v in doc["roles"].items() if not k.startswith("_")}
    applied = []
    for task in doc["roles"]["_tasks"]:
        for role, r in roles.items():
            current = conn.execute("""select pinned_model_id, pinned_provider, watch from models.preferences
                                      where task = %s and role = %s""", (task, role)).fetchone()
            if not current or (current["pinned_model_id"], current["pinned_provider"], current["watch"]) != \
                    (r["model"], r.get("provider"), r["watch"]):
                choose.set_preference(conn, task, pin=r["model"], provider=r.get("provider"), role=role,
                                      watch=r["watch"], note=r["description"])
                applied.append(f"{task}:{role}")
            conn.execute("""update models.preferences set label = %s, description = %s, signals = %s, priority = %s,
                              pinned_provider = %s
                            where task = %s and role = %s""",
                         (r["label"], r["description"], r["signals"], r.get("priority", 0), r.get("provider"), task, role))
    retired = doc.get("retired_roles") or {}
    for task in retired.get("_tasks", []):
        conn.execute("delete from models.preferences where task = %s and role = any(%s)", (task, retired["roles"]))
    for a in doc.get("affinities", []):
        conn.execute("""insert into models.affinities (model_id, scope, weight, reason) values (%s, %s, %s, %s)
                        on conflict (model_id, scope) do update set weight = excluded.weight, reason = excluded.reason""",
                     (a["model"], a.get("scope", "*"), a.get("weight", 1), a["reason"]))
    return {"profiles": len(doc["profiles"]), "roles_changed": applied, "affinities": len(doc.get("affinities", []))}


# --- close calls ----------------------------------------------------------------------------------------

def affinity(conn, model_id: str, task: str) -> int:
    row = conn.execute("""select coalesce(max(weight), 0) as w from models.affinities
                          where model_id = %s and scope in ('*', %s)""", (model_id, task)).fetchone()
    return row["w"]


def tie_margin(unit: str | None) -> float:
    return TIE_MARGIN.get(unit or "", ELO_TIE if unit and "elo" in unit.lower() else 1.0)


def tie_break(conn, task: str, rows: list[dict], score="quality", unit="quality_unit") -> list[dict]:
    """Close calls: every model within the tie margin of the current leader forms a group; inside the group
    Monsieur's affinity, then a subscription route, then the score decide. A model moved up gets
    reasons['tie_break']."""
    rest = sorted(rows, key=lambda r: -(r[score] if r[score] is not None else float("-inf")))
    out: list[dict] = []
    while rest:
        lead = rest[0]
        if lead[score] is None:
            out += rest
            break
        margin = tie_margin(lead.get(unit))
        group = [r for r in rest if r[score] is not None and lead[score] - r[score] <= margin]
        rest = [r for r in rest if r not in group]
        ordered = sorted(group, key=lambda r: (-affinity(conn, r["model_id"], task), not r.get("subscription"),
                                               -r[score]))
        for r in ordered:
            if r is not lead and ordered.index(r) < group.index(r):
                pref = affinity(conn, r["model_id"], task) > affinity(conn, lead["model_id"], task)
                why = (f'égalité avec {lead["model_id"]} ({lead[score]:.1f} vs {r[score]:.1f}, marge {margin:g}) : '
                       + ("préférence de Monsieur" if pref else "accès par abonnement"))
                r = {**r, "reasons": {**(r.get("reasons") or {}), "tie_break": why}}
            out.append(r)
    return out


# --- decision -------------------------------------------------------------------------------------------

def effective_policy(conn, model_id: str) -> str:
    row = conn.execute("""select coalesce(p.content_policy, c.content_policy) as cp from models.canonical c
                          left join models.profiles p using (model_id) where c.model_id = %s""", (model_id,)).fetchone()
    return row["cp"] if row else "standard"


def profile(conn, model_id: str) -> dict | None:
    return conn.execute("select * from models.profiles where model_id = %s", (model_id,)).fetchone()


def _role_line(conn, task: dict, p: dict) -> str:
    c = catalog.card(conn, p["pinned_model_id"], task["interface"], task["modes"])
    prof = profile(conn, p["pinned_model_id"])
    extra = f' ({prof["cost_note"]})' if prof and prof["cost_note"] else ""
    return f'{p["label"] or p["role"]} → {catalog.line(c)} : {p["description"] or ""}{extra}'.strip()


def decide(conn, task: str, intent: str, level: str | None = None) -> dict[str, Any]:
    """Free-text request -> role (objective) -> favourite model -> route, workflow and a brief for the orchestrator."""
    t = conn.execute("select * from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        raise KeyError(f"unknown task: {task}")
    doc = load()
    unrestricted = hits(intent, doc.get("unrestricted_signals", []))
    roles = conn.execute("select * from models.preferences where task = %s and pinned_model_id is not null",
                         (task,)).fetchall()
    if not any(r["signals"] or r["role"] == "default" for r in roles) or len(roles) < 2:
        if unrestricted:
            return {**choose.pick_required(conn, t, "unrestricted"), "signals": unrestricted}
        return choose.pick(conn, task, level)
    scored = sorted(((len(hits(intent, r["signals"])), r["priority"], r) for r in roles),
                    key=lambda x: (x[0], x[1]), reverse=True)
    chosen = scored[0][2] if scored[0][0] > 0 else next((r for r in roles if r["role"] == "default"), scored[0][2])
    warning = None
    if unrestricted and effective_policy(conn, chosen["pinned_model_id"]) == "standard":
        permissive = [r for r in roles if effective_policy(conn, r["pinned_model_id"]) != "standard"]
        if permissive:
            chosen = permissive[0]
        else:
            return {**choose.pick_required(conn, t, "unrestricted"), "signals": unrestricted}
    if unrestricted and effective_policy(conn, chosen["pinned_model_id"]) == "permissive":
        warning = "modèle réputé permissif, pas garanti sans restriction : à vérifier sur le résultat"
    answer = choose.pick(conn, task, role=chosen["role"])
    prof = profile(conn, chosen["pinned_model_id"])
    others = [r for r in roles if r["role"] != chosen["role"]]
    brief = "\n".join([f'Tâche {t["label"]} — rôles de Monsieur (choisis selon l\'objectif de la demande) :']
                      + [f'- {"[choisi] " if r["role"] == chosen["role"] else ""}{_role_line(conn, t, r)}'
                         for r in [chosen] + others])
    return {**answer, "role": chosen["role"], "role_label": chosen["label"],
            "matched_signals": hits(intent, chosen["signals"]), "unrestricted_signals": unrestricted,
            "warning": warning,
            "profile": {k: prof[k] for k in ("strengths", "weaknesses", "effort", "workflow", "access_note",
                                             "cost_note", "note")} if prof else None,
            "alternatives": [{"role": r["role"], "label": r["label"], "model_id": r["pinned_model_id"],
                              "signals_matched": hits(intent, r["signals"])} for r in others],
            "brief": brief}
