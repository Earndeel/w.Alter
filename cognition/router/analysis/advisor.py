"""The Router's advisor agent (owner, 2026-11-20: « le router doit avoir un vrai agent intelligent qui s'occupe de
comprendre les tenants et les aboutissants »).

The cycle's rules (tiers.py, alerts.py) see one thing at a time; the advisor reads the whole picture after each cycle
and after each choice of the owner — declared tiers, their quota substitutes, padlocks, the frontier with measured and
estimated subscription costs, what changed, what the owner already accepted or refused — and works out the
consequences (a substitute left behind by a new tier, an estimate a measure contradicts, a tier that no longer fits
the owner's rules…). It is one Walter Engine delegation (caller `guardian-router-advisor`, poste general/L3) that
investigates read-only and ends with a JSON verdict. Its proposals become 'advice' alerts sent on Telegram with
buttons; adopting one applies exactly one whitelisted action (OPS) through the Router's usual writers. It never
changes anything by itself: the owner decides (CLAUDE.md: Telegram proposals, never an automatic switch).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from walter_router import instance, paths

ENGINE_URL = os.environ.get("WALTER_ENGINE_API_URL", "http://127.0.0.1:8895")
CALLER = "guardian-router-advisor"      # policy machine_interfaces « guardian- »: a declared machine caller
TASK, LEVEL = "general", "L3"           # the owner's top text tier: understanding consequences is its job
BUDGET = 1500                           # seconds of work per run
MAX_PROPOSALS = 3
OWNER_DELAY = 90                        # after an owner's click: let a burst of clicks land before reading the state
OPS = ("set_quota_fallback", "set_level", "set_preference", "set_lock", "note")
LEVELS = ("L1", "L2", "L3")


# ---- the picture ---------------------------------------------------------------------------------------------------

def _pin(model_id, variant) -> str | None:
    return f"{model_id}/{variant}" if model_id and variant else model_id


def _aa(conn, model_id: str, variant: str) -> dict | None:
    r = conn.execute("""select b.score, b.cost from models.benchmarks b join models.latest_snapshots l using (snapshot_id)
                        where b.benchmark = 'aa_intelligence' and b.model_id = %s and b.variant = %s
                        order by b.score desc limit 1""", (model_id, variant or "")).fetchone()
    return dict(r) if r else None


def _routes(conn, pin: str | None) -> list[str]:
    if not pin:
        return []
    from walter_router.serve import execution
    mid, _, var = pin.partition("/")
    try:
        return [f'{r["provider"]}:{r.get("access")}' for r in execution.routes(conn, mid, var)]
    except Exception:  # noqa: BLE001 — unknown model: no route, which is the point to report
        return []


def state(conn, trigger: str = "manual", extra: dict | None = None) -> dict:
    """Everything the advisor needs, compact and in one snapshot of the index."""
    from walter_router.analysis import changes, knowledge
    from walter_router.analysis import select as sel
    levels = (knowledge.load().get("levels") or {}).get("general") or {}
    declared = {}
    for lv in LEVELS:
        d = levels.get(lv) or {}
        entry = {k: d.get(k) for k in ("pin", "provider", "fallback", "when_quota_spent", "evidence") if d.get(k)}
        for key in ("pin", "fallback", "when_quota_spent"):
            if d.get(key):
                mid, _, var = d[key].partition("/")
                entry[f"{key}_now"] = {"aa": _aa(conn, mid, var), "routes": _routes(conn, d[key])}
        declared[lv] = entry
    run = conn.execute("select run_id from models.latest_run").fetchone()
    tiers, frontier = [], []
    if run:
        for r in conn.execute("""select level, rank, model_id, variant, quality, real_cost, reasons from models.selection
                                 where run_id = %s and task = 'general' and level in ('L1', 'L2', 'L3', 'frontier')
                                 order by level, rank""", (run["run_id"],)):
            rs = r["reasons"] or {}
            sub = rs.get("subscription_cost") or {}
            row = {"pin": _pin(r["model_id"], r["variant"]), "score": r["quality"],
                   "cost_per_task": r["real_cost"] and round(r["real_cost"], 4),
                   "via": sub.get("provider") if sub.get("cost") == r["real_cost"] else (rs.get("provider") or "paid"),
                   **({"estimated_from": sub["estimated_from"]} if sub.get("estimated_from") else {})}
            if r["level"] == "frontier":
                frontier.append(row)
            else:
                tiers.append({"level": r["level"], **row, "role": rs.get("role"), "hold": rs.get("hold"),
                              "method_pick": rs.get("method_pick"), "quota_rule": rs.get("quota_rule")})
    subs = sel.load_subscription_costs(conn)
    prefs = [{"task": r["task"], "role": r["role"], "pin": _pin(r["pinned_model_id"], r["pinned_variant"]),
              "provider": r["pinned_provider"], "locked": r["locked"]}
             for r in conn.execute("""select task, role, pinned_model_id, pinned_variant, pinned_provider, locked
                                      from models.preferences where pinned_model_id is not null order by task, role""")]
    chg = changes.events(conn)
    recent = [dict(r) for r in conn.execute(
        """select kind, task, role, subject, status, verdict_note, evidence->'why' as why,
                  evidence->>'title_fr' as title, to_char(last_seen, 'YYYY-MM-DD') as seen
           from models.alerts where kind in ('tier', 'pareto', 'advice', 'challenger', 'new_best', 'nerf')
             and last_seen > now() - interval '30 days' and status <> 'baseline'
           order by last_seen desc limit 60""")]
    try:
        rules = (paths.ROOT / "docs" / "TIERS.md").read_text()
    except OSError:
        rules = ""
    return {"now": datetime.now(timezone.utc).isoformat(timespec="minutes"), "trigger": trigger, "detail": extra or {},
            "declared_text_tiers": declared, "method_tiers_last_cycle": tiers, "text_frontier": frontier[:30],
            "subscription_cost_ratios": [{"route_provider": p, "model_id": m, "ratio": v.get("ratio"),
                                          "source": v.get("source"), "estimated_from": v.get("estimated_from")}
                                         for (p, m), v in sorted(subs.items())],
            "preferences": prefs,
            "changes_since_previous_cycle": {"new": sorted(chg["new"])[:40], "nerf": chg["nerf"],
                                             "price_drop": chg["price_drop"], "rebased": chg["rebased"]},
            "recent_alerts_and_owner_answers": recent, "tier_rules": rules}


BRIEF = """Tu es le conseiller du Walter Router de {owner}, sur sa VM. Le Router choisit le modèle de chaque tâche
(niveaux texte L1/L2/L3, spécialistes, image, vidéo, voix…) à partir des classements (Artificial Analysis…), des prix et
des abonnements de {owner}. Ses règles automatiques regardent une chose à la fois ; toi, tu comprends les tenants et les
aboutissants : ce qu'un changement implique ailleurs, ce qui est devenu incohérent, ce que {owner} n'a pas vu.

Déclencheur : {trigger}. L'état complet est ci-dessous (un seul instantané de l'index ; les règles des niveaux, écrites
par {owner}, sont dans `tier_rules`).

Ce que tu cherches (exemples, pas une liste fermée) :
- un repli « quota épuisé » (`when_quota_spent`) ou un `fallback` resté sur un ancien modèle alors qu'un meilleur existe
  sur le même abonnement, ou qui n'a plus de route, ou qui ferait descendre le niveau sous le niveau inférieur ;
- un niveau qui ne respecte plus ses règles (L1 < L2 < L3 en score ; L2 sur un autre abonnement que L3 ; même prix ±25 %
  et jamais un score plus bas pour L1/L2) ;
- un coût d'abonnement estimé (`estimated_from`) qui change une décision, ou qu'une mesure contredit ;
- un recalcul de l'index (rebased) qui fausse une comparaison ; une proposition déjà refusée par {owner} qu'il ne faut
  pas reproposer (regarde `recent_alerts_and_owner_answers`) ;
- les conséquences du choix que {owner} vient de faire (détail du déclencheur).

Comment travailler : vérifie avant de proposer, en lecture seule — `walter-router pick general --level L3`,
`walter-router route <tâche>`, `walter-router dossier <tâche>`, `walter-router plans`, `walter-router library`,
`cd {root} && venv/bin/python -c "…"` pour lire la base via `walter_router.store.db`. Tu ne modifies RIEN (ni fichier,
ni base, ni service), tu n'envoies aucun message, tu ne fais aucun appel payant : {owner} décide, sur Telegram, avec
les boutons que le Router fabrique à partir de ton verdict.

Propose peu : au plus {max} propositions, seulement celles qui changent vraiment quelque chose pour {owner}, chacune
avec UNE action parmi :
- {{"op": "set_quota_fallback", "level": "L1|L2|L3", "pin": "model_id/variant"}} — le modèle qui prend le relais du
  niveau quand son abonnement est épuisé (et en cas de panne de tous ses fournisseurs) ;
- {{"op": "set_level", "level": "L1|L2|L3", "pin": "model_id/variant", "provider": "route_provider ou null",
  "when_quota_spent": "model_id/variant ou null"}} — changer un niveau texte ;
- {{"op": "set_preference", "task": "<tâche>", "role": "<rôle>", "pin": "model_id[/variant]", "provider": null}} ;
- {{"op": "set_lock", "task": "<tâche>", "role": "<rôle>", "locked": true|false}} ;
- {{"op": "note"}} — une information importante sans action.
Les identifiants viennent de l'état ou de tes vérifications (jamais inventés) ; le Router refuse une action dont le
modèle n'a pas de route.

Termine par un seul objet JSON :
{{"summary_fr": "deux phrases simples pour {owner} : ce que tu as regardé et ce que tu en conclus",
 "proposals": [{{"title_fr": "titre court", "why_fr": "pourquoi, chiffres à l'appui (score AA, $/tâche)",
                "consequences_fr": "ce qui change concrètement si {owner} accepte", "action": {{...}}}}]}}
Rien à proposer : "proposals": [].

## État
```json
{state}
```"""


def brief(st: dict) -> str:
    return BRIEF.format(owner=instance.owner(), trigger=st.get("trigger"), root=paths.ROOT, max=MAX_PROPOSALS,
                        state=json.dumps(st, ensure_ascii=False, indent=1, default=str))


def verdict_of(output: str) -> dict | None:
    """The agent's closing JSON: the last object carrying `proposals`."""
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"\{", output or ""))):
        try:
            obj, _ = decoder.raw_decode(output[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("proposals"), list):
            return obj
    return None


# ---- actions --------------------------------------------------------------------------------------------------------

def _callable(conn, task: str, pin: str) -> bool:
    from walter_router.serve.choose import routes_for
    t = conn.execute("select interface, modes from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        return False
    mid, _, var = pin.partition("/")
    if t["interface"] == "chat" and not _aa(conn, mid, var) and var:
        return False                                      # a reasoning level the index does not know
    return bool(routes_for(conn, mid, t["interface"], t["modes"] or None).get("callable"))


def validate(conn, action: dict) -> str | None:
    """None when the action can be applied as is, else why not."""
    if not isinstance(action, dict) or action.get("op") not in OPS:
        return "action inconnue"
    op = action["op"]
    if op == "note":
        return None
    if op in ("set_quota_fallback", "set_level"):
        from walter_router.analysis import knowledge
        if action.get("level") not in LEVELS:
            return "niveau inconnu"
        lv = ((knowledge.load().get("levels") or {}).get("general") or {}).get(action["level"]) or {}
        for key in ("pin", "when_quota_spent"):
            pin = action.get(key)
            if key == "pin" or pin:
                if not isinstance(pin, str) or "/" not in pin:
                    return f"{key} doit être model_id/variant"
                if not _callable(conn, "general", pin):
                    return f"{pin} n'a pas de route"
        if op == "set_quota_fallback" and action["pin"] == lv.get("pin"):
            return "le relais serait le modèle du niveau lui-même"
        if op == "set_quota_fallback" and action["pin"] == lv.get("when_quota_spent") == lv.get("fallback"):
            return "déjà en place"
        if op == "set_level" and action["pin"] == lv.get("pin"):
            return "déjà en place"
        return None
    task, role = action.get("task"), action.get("role") or "default"
    if not conn.execute("select 1 from models.tasks where task = %s", (task,)).fetchone():
        return "tâche inconnue"
    if op == "set_lock":
        return None if isinstance(action.get("locked"), bool) else "locked doit être true ou false"
    pin = action.get("pin")
    if not isinstance(pin, str) or not pin:
        return "pin manquant"
    return None if _callable(conn, task, pin) else f"{pin} n'a pas de route"


def subject(action: dict) -> str:
    """One proposal = one action: the same action proposed twice is the same alert (a refusal stays a refusal)."""
    keys = [k for k in ("op", "level", "task", "role", "pin", "provider", "when_quota_spent", "locked") if k in action]
    return ":".join(str(action.get(k)) for k in keys)[:300]


def apply(conn, action: dict, note: str) -> dict:
    """The owner adopted the advice: one action through the Router's usual writers."""
    err = validate(conn, action)
    if err and err != "déjà en place":
        raise ValueError(err)
    op = action["op"]
    if op == "note" or err:
        return {"applied": False, "op": op, **({"why": err} if err else {})}
    from walter_router.analysis import alerts, knowledge
    from walter_router.serve.choose import set_preference
    if op == "set_quota_fallback":
        lv = knowledge.load()["levels"]["general"][action["level"]]
        knowledge.set_level("general", action["level"], lv["pin"], why=note, provider=lv.get("provider"),
                            fallback=action["pin"], when_quota_spent=action["pin"])
        return {"applied": True, "op": op, "level": action["level"], "when_quota_spent": action["pin"]}
    if op == "set_level":
        spent = action.get("when_quota_spent")
        knowledge.set_level("general", action["level"], action["pin"], why=note, provider=action.get("provider"),
                            **({"when_quota_spent": spent, "fallback": spent} if spent else {}))
        set_preference(conn, "general", pin=action["pin"], provider=action.get("provider"), role=action["level"],
                       watch="dominance", note=note)
        return {"applied": True, "op": op, "level": action["level"], "pin": action["pin"]}
    if op == "set_preference":
        set_preference(conn, action["task"], pin=action["pin"], provider=action.get("provider"),
                       role=action.get("role") or "default", note=note)
        return {"applied": True, "op": op, "task": action["task"], "pin": action["pin"]}
    out = alerts.set_lock(conn, action["task"], action.get("role"), action["locked"])
    return {"applied": True, "op": op, **out}


def record(conn, verdict: dict, run: dict) -> list[dict]:
    """The agent's proposals as 'advice' alerts (open → sent on Telegram); refused actions are kept in the run log."""
    from walter_router.analysis import alerts
    kept = []
    for p in (verdict.get("proposals") or [])[:MAX_PROPOSALS]:
        if not isinstance(p, dict):
            continue
        action = p.get("action") or {"op": "note"}
        err = validate(conn, action)
        if err:
            kept.append({"title_fr": p.get("title_fr"), "refused": err, "action": action})
            continue
        ev = {"title_fr": str(p.get("title_fr") or "")[:200], "why_fr": str(p.get("why_fr") or "")[:900],
              "consequences_fr": str(p.get("consequences_fr") or "")[:600], "action": action,
              "trigger": run.get("trigger"), "run_at": run.get("at")}
        new = alerts.record(conn, "advice", action.get("task") or "general", subject(action), ev, "open",
                            action.get("level") or action.get("role") or "")
        kept.append({"title_fr": ev["title_fr"], "action": action, "new": new})
    return kept


# ---- running ---------------------------------------------------------------------------------------------------------

def _engine_token() -> str:
    root = instance._walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return (Path(root) / "bootstrap" / "engine" / "api.token").read_text().strip()


def delegate(goal: str, key: str, budget: int = BUDGET) -> dict:
    """One Walter Engine delegation (Engine API, the declared door to the runtime)."""
    body = {"version": 1, "op": "delegate", "caller": CALLER,
            "delegation": {"version": 1, "goal": goal, "task": TASK, "level": LEVEL, "budget_seconds": budget,
                           "idempotency_key": key, "parent": {"depth": 0}}}
    req = Request(ENGINE_URL.rstrip("/") + "/v1", data=json.dumps(body).encode(),
                  headers={"Authorization": "Bearer " + _engine_token(), "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=budget + 120) as r:
            out = json.load(r)
    except Exception as exc:  # noqa: BLE001 — engine down: a failed run, said as such
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    res = out.get("result") or out
    return {"ok": bool(res.get("ok")), "output": res.get("output") or "", "status": res.get("status"),
            "reason": res.get("reason"), "error": res.get("error"), "tools": len(res.get("tools") or [])}


def _log(entry: dict) -> None:
    try:
        f = instance.state_file("advisor/runs.jsonl")
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — the log is a trace, never a reason to fail the run
        pass


def run(trigger: str = "manual", extra: dict | None = None, dry_run: bool = False, notify: bool = True) -> dict:
    from walter_router.analysis import telegram
    from walter_router.store import db
    started = time.time()
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        st = state(conn, trigger, extra)
    goal = brief(st)
    if dry_run:
        return {"trigger": trigger, "brief_chars": len(goal), "state": st}
    ran = delegate(goal, f"router-advisor-{trigger}-{int(started)}"[:200])
    v = verdict_of(ran.get("output") or "")
    entry = {"at": at, "trigger": trigger, "detail": extra, "seconds": round(time.time() - started),
             "engine": {k: ran.get(k) for k in ("ok", "status", "reason", "error", "tools")}}
    if not v:
        _log({**entry, "verdict": None, "tail": (ran.get("output") or "")[-600:]})
        return {**entry, "verdict": None}
    with db.connect() as conn:
        kept = record(conn, v, {"trigger": trigger, "at": at})
        sent = telegram.notify(conn) if notify and any(k.get("new") for k in kept) else {"sent": 0}
        conn.commit()
    entry.update(summary_fr=v.get("summary_fr"), proposals=kept, notify=sent)
    _log(entry)
    return entry


def launch(trigger: str, extra: dict | None = None, delay: int = 0) -> bool:
    """Start a run in its own transient unit (the cycle or the Telegram click never waits for it). One at a time."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("WALTER_ROUTER_ADVISOR") == "off":
        return False
    if subprocess.run(["systemctl", "is-active", "--quiet", "walter-router-advisor"]).returncode == 0:
        return False
    cmd = [str(paths.ROOT / "bin" / "walter-router"), "advisor", "run", "--trigger", trigger]
    if extra:
        cmd += ["--detail", json.dumps(extra, ensure_ascii=False, default=str)[:2000]]
    if delay:
        cmd = ["sh", "-c", f"sleep {int(delay)}; exec \"$@\"", "sh", *cmd]
    r = subprocess.run(["systemd-run", "--unit", "walter-router-advisor", "--collect", "--quiet",
                        f"--property=RuntimeMaxSec={BUDGET + 600}", *cmd], capture_output=True, text=True, timeout=30)
    return r.returncode == 0
