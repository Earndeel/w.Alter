"""One JSON dossier per task, rebuilt at every refresh (models.dossiers): everything the router / orchestrator
needs to decide in a single read — the owner's roles and model fiches first, then the weighted candidates with their
evidence, prices, access and constraints, and the decision rules in plain words."""
from __future__ import annotations

import json
from typing import Any

from walter_router.analysis import catalog
from walter_router.analysis import knowledge
from walter_router import instance

RULES = [
    "1. Les favoris de {owner} priment : choisir le rôle qui correspond à l'objectif de la demande (signaux), "
    "sinon le rôle « default ».",
    "2. Sans favori : prendre le premier candidat (score composite pondéré multi-benchmarks).",
    "3. Égalité (écart dans la marge) : préférence de {owner}, puis accès par abonnement (Codex, crédits Flow).",
    "4. Workflow d'un modèle (références, prompt adapté…) : le planifier avant de générer.",
    "5. Demande sans restriction : uniquement un modèle 'unrestricted' (ou 'permissive' avec avertissement).",
    "6. Ne jamais changer un favori sans l'accord de {owner}.",
]


def build(conn, task: str, run_id: int, n: int = 8) -> dict[str, Any]:
    t = conn.execute("select * from models.tasks where task = %s", (task,)).fetchone()
    boards = conn.execute("""select benchmark, bench_task, weight, is_primary from models.task_benchmarks
                             where task = %s order by weight desc""", (task,)).fetchall()
    roles = []
    for p in conn.execute("""select * from models.preferences where task = %s order by (role = 'default') desc,
                             priority desc, role""", (task,)):
        prof = knowledge.profile(conn, p["pinned_model_id"]) if p["pinned_model_id"] else None
        card = catalog.card(conn, p["pinned_model_id"], t["interface"], t["modes"]) if p["pinned_model_id"] else None
        roles.append({"role": p["role"], "label": p["label"], "for": p["description"] or p["note"],
                      "signals": p["signals"], "model_id": p["pinned_model_id"], "provider": p["pinned_provider"],
                      "objective": p["objective"], "line": catalog.line(card) if card else None,
                      "profile": {k: prof[k] for k in ("strengths", "weaknesses", "effort", "workflow", "access_note",
                                                       "cost_note", "content_policy")} if prof else None})
    cands = []
    for r in conn.execute("""select * from models.selection where run_id = %s and task = %s and level = 'best'
                             order by rank limit %s""", (run_id, task, n)):
        card = catalog.card(conn, r["model_id"], t["interface"], t["modes"])
        reasons = r["reasons"] or {}
        cands.append({"rank": r["rank"], "model_id": r["model_id"], "name": r["display_name"],
                      "composite": r["quality"], "boards": reasons.get("boards"),
                      "evidence_weight": reasons.get("evidence_weight"), "tie_break": reasons.get("tie_break"),
                      "route": {"subscription": r["subscription"], "paid": r["provider"], "offer": r["offer_key"],
                                "cost": r["real_cost"], "cost_unit": r["cost_unit"]},
                      "line": catalog.line(card), "open_weights": card["open_weights"],
                      "content_policy": knowledge.effective_policy(conn, r["model_id"]),
                      "affinity": knowledge.affinity(conn, r["model_id"], task)})
    levels = {r["level"]: {"model_id": r["model_id"], "variant": r["variant"], "quality": r["quality"],
                           "unit": r["quality_unit"], "provider": r["subscription"] or r["provider"]}
              for r in conn.execute("""select * from models.selection where run_id = %s and task = %s and rank = 1
                                       and level in ('L1', 'L2', 'L3', 'value')""", (run_id, task))}
    method = None
    if task == "general":
        from walter_router.analysis import tiers
        method = {"doc": "docs/TIERS.md", "summary": tiers.__doc__.strip().split("\n\n")[1],
                  "frontier": [{"model_id": r["model_id"], "variant": r["variant"], "score": round(r["quality"], 1),
                                "cost": round(r["real_cost"] or 0, 3),
                                "marginal": (r["reasons"] or {}).get("marginal")}
                               for r in conn.execute("""select * from models.selection where run_id = %s and task = 'general'
                                                        and level = 'frontier' order by rank""", (run_id,))]}
    ranking = None
    if task != "general" and boards:
        ranking = _ranking(conn, t, {r["model_id"] for r in roles if r.get("model_id")}, n)
    postes_doc = None
    if task == "general":
        from walter_router.analysis import postes as postes_mod
        postes_doc = {p: postes_mod.rank(conn, p, 3) for p in ("orchestrator", "agent_worker")}
    return {"task": task, "label": t["label"], "tier_method": method, "postes": postes_doc, "interface": t["interface"], "modes": t["modes"],
            "default_objective": t["default_objective"],
            "boards": [{"board": f'{b["benchmark"]}:{b["bench_task"]}', "weight": b["weight"],
                        "primary": b["is_primary"]} for b in boards],
            "requirements": t.get("requirements") or {}, "consumers": t.get("consumers"),
            "roles": roles, "candidates": cands, "ranking": ranking, "levels": levels, "rules": [r.format(owner=instance.owner()) for r in RULES], "run_id": run_id}


def _ranking(conn, t: dict, pinned: set[str], n: int) -> list[dict]:
    """Every measured model of the task in composite order (callable or not), the owner's pinned models always shown
    with their place: what a proposal would compare. `candidates` keeps the selection (#1 only for specialised tasks)."""
    from walter_router.analysis import scoring
    from walter_router.analysis import select as sel
    offers = sel.load_offers(conn, sel.latest_snapshots(conn))
    out = []
    for i, c in enumerate(scoring.composite(conn, t["task"])):
        if i >= n and c["model_id"] not in pinned:
            continue
        mine = [o for o in offers.get(c["model_id"], []) if o["interface"] == t["interface"]]
        route = sel.media_route(mine, t["interface"], t["modes"]) if t["interface"] != "chat" else None
        out.append({"rank": i + 1, "model_id": c["model_id"], "composite": c["composite"],
                    "pinned": c["model_id"] in pinned, "callable": bool(mine),
                    "providers": sorted({o["provider"] for o in mine}),
                    "price": (route or {}).get("paid") and {k: route["paid"].get(k) for k in ("cost", "unit", "provider")},
                    "boards": {k: {x: v[x] for x in ("score", "unit", "rank", "of", "wer_pct", "latency_ms", "list_price",
                                                     "price_unit", "host") if x in v} for k, v in c["boards"].items()}})
    for m in sorted(pinned - {r["model_id"] for r in out}):
        out.append({"rank": None, "model_id": m, "pinned": True, "measured": False,
                    "note": "absent des classements de cette tâche (une variante proche peut l'être)"})
    return out


def build_all(conn, run_id: int) -> int:
    n = 0
    for t in conn.execute("select task from models.tasks where default_objective <> 'tool'").fetchall():
        doc = build(conn, t["task"], run_id)
        conn.execute("""insert into models.dossiers (run_id, task, doc) values (%s, %s, %s::jsonb)
                        on conflict (run_id, task) do update set doc = excluded.doc, built_at = now()""",
                     (run_id, t["task"], json.dumps(doc, default=str, ensure_ascii=False)))
        n += 1
    return n


def latest(conn, task: str) -> dict | None:
    row = conn.execute("select doc from models.latest_dossiers where task = %s", (task,)).fetchone()
    return row["doc"] if row else None
