"""A recommendation in the proposal message (Monsieur, 2026-10-16: « à la place de 'meilleur sur les 3 axes', ajoute
ta recommandation personnelle par rapport à notre stack »).

Written once per proposal by the router's own economic model (L1, GPT-6 Luna via the Codex subscription: no marginal
cost) from FACTS about Monsieur's stack — what uses the task today, measured volume, per-call and monthly cost of both
options, fallbacks in place, the 3-axis comparison — then stored in the alert (never regenerated at each render).
A deterministic sentence is used when the model is unreachable.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

from . import execution
from .alerts import HERMES

USES = {"decision": "comprendre les demandes de Monsieur et choisir le modèle (Walter Router, chaîne de décision : "
                    "modèle retenu, puis Mercury Decide gratuit, puis Clef sur Workers AI)",
        "decision_vision": "aucun usage en production pour l'instant (prévu : navigation web rapide, tri d'images en masse)"}
EVAL = __import__("pathlib").Path(__file__).resolve().parent.parent / "eval" / "decision_results.json"


def ask_l1(conn, prompt: str, source: str, timeout: int = 240) -> str | None:
    """One-shot answer from the economic tier (L1) through Hermes, as craft_prompt does."""
    from . import choose
    d = choose.pick(conn, "general", "L1")
    route = next((r for r in execution.routes(conn, d["model_id"], d.get("variant") or "")
                  if r.get("probe_ok") is not False), None)
    if not route:
        return None
    cmd = [str(HERMES), "chat", "-q", prompt, "--oneshot", "-Q", "--provider", route["hermes_provider"], "-m",
           route["model"], "-t", "memory", "--max-turns", "1", "--source", source]
    if route.get("reasoning"):
        cmd += ["--reasoning", route["reasoning"]]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         env={**os.environ, "HOME": "/root", "HERMES_HOME": "/root/.hermes", "WALTER_ROUTER_CHILD": "1"})
    lines = [ln for ln in re.sub(r"\x1b\[[0-9;]*m", "", out.stdout).splitlines()
             if ln.strip() and not ln.startswith(("session_id:", "⚠", "Warning:")) and "hermes doctor" not in ln]
    text = " ".join(lines).strip().strip('"')
    return text or None


def _per_call(point: dict) -> float | None:
    """Same basis for both models: AA cost per task (AA cost per 1M tasks / 1e6)."""
    return point["cost"] / 1e6 if point.get("cost") is not None else None


def _volume(conn, task: str) -> float:
    """Decisions per day attributable to this task over the last 14 days."""
    if task != "decision":
        return 0.0
    n = conn.execute("""select count(distinct coalesce(call_id, session_id || seq::text)) n from walter_logs.events
                        where tool in ('walter_route', 'walter_run', 'walter_generate')
                        and occurred_at > now() - interval '30 days'""").fetchone()["n"]
    return n / 30


def facts(conn, alert: dict, new: dict, cur: dict) -> dict:
    per_new, per_cur = _per_call(new), _per_call(cur)
    evals = json.loads(EVAL.read_text()) if EVAL.exists() else {}
    vol = _volume(conn, alert["task"])
    month = (lambda c: round(c * vol * 30, 4) if c is not None else None)
    return {"tâche": alert["task"], "usage_actuel": USES.get(alert["task"], alert["task"]),
            "décisions_par_jour_mesurées_sur_30_jours": round(vol, 2),
            "proposé": {"nom": new["name"], "intelligence_AA_Decision": round(new["index"], 1), "ms_par_décision": new["ms"],
                        "coût_AA_par_million_de_tâches": round(new["cost"], 1), "lit_les_images": new["images"],
                        "coût_par_décision_usd": per_new, "coût_mensuel_estimé_usd": month(per_new)},
            "actuel": {"nom": cur["name"], "intelligence_AA_Decision": round(cur["index"], 1), "ms_par_décision": cur["ms"],
                       "coût_AA_par_million_de_tâches": round(cur["cost"], 1), "lit_les_images": cur["images"],
                       "coût_par_décision_usd": per_cur, "coût_mensuel_estimé_usd": month(per_cur)},
            "test_maison_30_demandes": {new["name"]: evals.get(new["model_id"], {}).get("tasks", "non testé"),
                                        cur["name"]: evals.get(cur["model_id"], {}).get("tasks", "non testé")},
            "secours_en_place": "Mercury Decide (gratuit, OpenRouter) puis Clef (Workers AI, allocation gratuite)",
            "contexte": "Monsieur décide lui-même de chaque changement (boutons Telegram). Le router ne change jamais "
                        "de modèle seul. Il préfère les choix Pareto à coût réel (gratuit = 0 $)."}


def fallback_text(new: dict, cur: dict) -> str:
    from .decision_pareto import dominates
    if dominates(new, cur):
        return f"Passer à {new['name']} : meilleur sur les trois axes, sans contrepartie pour ta stack."
    return f"Garder {cur['name']} tant que le gain d'intelligence ne justifie pas l'écart de prix ou de vitesse."


def recommendation(conn, alert: dict, new: dict, cur: dict) -> str:
    """Stored in the alert's evidence ('reco'); computed once."""
    if (alert.get("evidence") or {}).get("reco"):
        return alert["evidence"]["reco"]
    f = facts(conn, alert, new, cur)
    prompt = ("Tu conseilles Monsieur sur le choix d'un modèle pour son router personnel. Voici les faits, en JSON :\n"
              f"{json.dumps(f, ensure_ascii=False)}\n\n"
              "Donne TA recommandation en une ou deux phrases courtes, en français, en tutoyant Monsieur : commence par "
              "« Passer à <nom> » ou « Garder <nom> », puis la raison qui compte vraiment pour SA stack (usage réel, "
              "volume, coût mensuel, vitesse, besoin d'images). Pas de chiffres déjà connus répétés inutilement, pas de "
              "liste, pas de guillemets. Ne dis « gratuit » ou « coût nul » que pour un modèle réellement gratuit ; un coût "
              "mensuel nul faute d'usage se dit « faute d'usage ». Réponds uniquement par la recommandation.")
    try:
        text = ask_l1(conn, prompt, "walter-router-reco")
    except Exception:  # noqa: BLE001 — a rule-based sentence is better than nothing
        text = None
    text = text if text and 15 < len(text) < 400 else fallback_text(new, cur)
    conn.execute("update models.alerts set evidence = evidence || jsonb_build_object('reco', %s::text) where alert_id = %s",
                 (text, alert["alert_id"]))
    return text
