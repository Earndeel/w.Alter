"""Targeted reassessment during a run (POST /v1/reassess): the engine tells Context something changed (a failure, a
sub-agent's alternative, a contradiction with Memory, information that arrived, a new objective, an interruption)
and asks whether the plan still holds. Never a full preflight:

  1. a deterministic relevance gate says `asked: false` + why when nothing relevant changed (information already
     known, nothing open to resume, same objective, a failure already assessed…);
  2. a DecisionState restricted to what the trigger touches is built from the session's WorkingState;
  3. Walter Decision (walter-llm /v1/decisions) is asked ONLY the signals that fit the trigger — `ask=[ids]` of the
     `turn` occasion (the occasions are a closed set of Core's registry: turn / incoming / outgoing / document /
     result; Context declares no new one). No generalist model;
  4. the answer is memoised by (state version, trigger): the same reassessment is never asked twice.

`decide` is injectable (tests, bench); the default is walter_memory.llm.decide on the Router's decision chain.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

from . import decision_state as DS
from .config import state_settings
from .state import OPEN_TASK, manager

TRIGGERS = ("failure", "subagent.alternative", "memory.contradiction", "info.arrived", "objective.changed",
            "interrupted", "external")
# trigger → the `turn` signals it concerns (ids declared by Context, Router, Memory in their manifest/decisions.json)
ASK = {"failure": ["context.plan", "context.needs", "context.extensive"],
       "subagent.alternative": ["context.plan", "context.needs"],
       "memory.contradiction": ["context.plan", "context.needs", "context.domain", "context.horizon"],
       "info.arrived": ["context.plan", "context.needs"],
       "objective.changed": ["context.plan", "context.needs", "context.extensive", "context.domain", "context.horizon",
                             "router.tier"],
       "interrupted": ["memory.resume", "context.plan"],
       "external": ["context.plan", "context.needs"]}
LEVEL = {"none": "L0", "last_exchange": "L1", "thread": "L2", "thread_and_memory": "L3"}
NEED_MIN = 0.5
_MEMO: "OrderedDict[str, dict]" = OrderedDict()
_LOCK = threading.Lock()


def _norm(t) -> str:
    return " ".join(str(t or "").lower().split())


def _digest(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:20]


def trigger_text(tr: dict) -> str:
    kind = tr.get("kind")
    detail = next((tr[k] for k in ("text", "error", "alternative", "goal", "details", "reason", "where") if tr.get(k)), "")
    label = {"failure": "Échec en cours d'exécution", "subagent.alternative": "Un sous-agent propose une autre voie",
             "memory.contradiction": "La mémoire contredit l'état de travail", "info.arrived": "Une information est arrivée",
             "objective.changed": "L'objectif a changé", "interrupted": "L'exécution a été interrompue",
             "external": "Événement externe"}.get(kind, str(kind))
    return f"{label} : {' '.join(str(detail).split())[:400]}" if detail else label


def gate(trigger: dict, st: dict, facts: dict) -> tuple[bool, str]:
    """(relevant, reason). Deterministic: no model is asked unless the new state differs in what the trigger touches."""
    kind = trigger.get("kind")
    if kind not in TRIGGERS:
        return False, f"déclencheur inconnu : {str(kind)[:40]}"
    known = {_norm(x["text"]) for s in ("information", "observations", "decisions") for x in st[s] if not x.get("stale")}
    if kind == "failure":
        what = _norm(trigger.get("where") or trigger.get("tool")) + "|" + _norm(trigger.get("error"))[:120]
        seen = st["operation"].setdefault("reassessed_failures", [])
        if not (trigger.get("error") or trigger.get("where") or trigger.get("tool")):
            return False, "échec sans détail : rien à réévaluer"
        if what in seen:
            return False, "même échec déjà évalué dans cette session"
        return True, "nouvel échec"
    if kind == "subagent.alternative":
        alt = _norm(trigger.get("alternative") or trigger.get("text"))
        if not alt:
            return False, "aucune alternative décrite"
        if alt in known or any(alt == _norm(o["text"]) for o in st["objectives"]):
            return False, "alternative déjà connue de l'état"
        return True, "alternative nouvelle"
    if kind == "memory.contradiction":
        if not (st["contradictions"] or trigger.get("text") or trigger.get("details") or facts.get("contradiction")):
            return False, "aucune contradiction dans l'état ni dans le déclencheur"
        return True, "contradiction à trancher"
    if kind == "info.arrived":
        txt = _norm(trigger.get("text") or facts.get("text") or trigger.get("details"))
        if not txt:
            return False, "information vide"
        if txt in known:
            return False, "information déjà connue de l'état"
        return True, "information nouvelle"
    if kind == "objective.changed":
        goal = _norm(trigger.get("goal") or trigger.get("text"))
        active = next((_norm(o["text"]) for o in st["objectives"] if o.get("status") == "active"), "")
        last = st["operation"].get("reassessed_objective")
        if not goal and not active:
            return False, "aucun objectif"
        if (goal or active) == last:
            return False, "objectif inchangé depuis la dernière réévaluation"
        return True, "objectif différent"
    if kind == "interrupted":
        if not any(t.get("status") in OPEN_TASK for t in st["tasks"]) and not st["pending"]:
            return False, "rien d'ouvert à reprendre (aucune tâche ni élément en attente)"
        return True, "tâches ou éléments en attente à reprendre"
    return (True, "événement externe") if (trigger.get("text") or trigger.get("details")) else (False, "événement externe sans contenu")


def _default_decide(*a, **kw):
    from walter_memory import llm
    return llm.decide(*a, **kw)


def _decisions(res: dict) -> dict:
    from .preflight import resolved                   # the Decision Resolver's answers when relations are declared
    sig = resolved(res)
    out = {}
    plan = (sig.get("context.plan") or {}).get("choice")
    if plan in LEVEL:
        out["plan"], out["context_level"] = plan, LEVEL[plan]
    needs = (sig.get("context.needs") or {}).get("probabilities") or {}
    if needs:
        out["capabilities"] = sorted(k for k, p in needs.items() if isinstance(p, (int, float)) and p >= NEED_MIN)
    for sid, key in (("context.domain", "domain"), ("context.horizon", "horizon"), ("router.tier", "tier")):
        c = (sig.get(sid) or {}).get("choice")
        if c:
            out[key] = c
    for sid, key in (("context.extensive", "extensive"), ("memory.resume", "resume")):
        v = (sig.get(sid) or {}).get("noul")
        if isinstance(v, (int, float)):
            out[key] = round(float(v), 2) >= NEED_MIN
            out[key + "_p"] = round(float(v), 2)
    return out


def render(kind: str, reason: str, d: dict, ds: dict) -> str:
    """Short French text for the model's context: what changed, what the decision says, what is still unknown."""
    bits = [f"Réévaluation ({kind}) : {reason}."]
    if d.get("context_level"):
        bits.append(f"Contexte nécessaire : {d['context_level']}.")
    if d.get("capabilities") is not None:
        bits.append("Capacités utiles : " + (", ".join(d["capabilities"]) or "aucune en plus") + ".")
    if d.get("extensive"):
        bits.append("Recherche étendue recommandée.")
    if d.get("resume"):
        bits.append("Une tâche ouverte semble à reprendre.")
    if ds["contradictions"]:
        bits.append("Contradictions : " + " ; ".join(c["text"][:100] for c in ds["contradictions"][:2]) + ".")
    if ds["unknowns"]:
        bits.append("Inconnu : " + " ; ".join(ds["unknowns"][:3]) + ".")
    return " ".join(bits)


def reassess(body: dict, *, decide=None, mgr=None, cfg: dict | None = None, chain=None) -> dict:
    cfg = cfg or state_settings()
    mgr = mgr or manager()
    sid = body.get("session_id")
    trigger = body.get("trigger")
    if not isinstance(sid, str) or not sid or not isinstance(trigger, dict):
        raise ValueError("session_id and trigger are required")
    facts_in = body.get("facts") if isinstance(body.get("facts"), dict) else {}
    st = mgr.get(sid, body.get("thread_id"))
    kind = trigger.get("kind")
    key = _digest(sid, st["version"], trigger, facts_in)
    with _LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            hit = dict(_MEMO[key])
            return {**hit, "asked": False, "reason": f"déjà évalué à la version {st['version']} (réponse mémorisée)",
                    "memoized": True, "version": st["version"]}
    relevant, reason = gate(trigger, st, facts_in)
    ds = DS.build(trigger_text(trigger), working=st, occasion="reassess", trigger=trigger,
                  capabilities=body.get("capabilities"), use=body.get("inputs"))
    out = {"asked": False, "reason": reason, "version": st["version"], "decision_state": DS.compact(ds, 1400), "decisions": {},
           "text": ""}
    if not relevant:
        out["text"] = f"Réévaluation ({kind}) non nécessaire : {reason}."
        _remember(key, out)
        return out
    if body.get("privacy_class") == "local_only":
        out.update(reason="privacy local_only : aucun modèle externe", text=f"Réévaluation ({kind}) non faite : local_only.")
        return out
    ask = ASK[kind]
    facts = sorted(set(ds["facts"]) | ({"open_task"} if any(t.get("status") in OPEN_TASK for t in st["tasks"]) else set()))
    state = {"new_message": trigger_text(trigger), "decision_state": out["decision_state"]}
    t0 = time.perf_counter()
    try:
        res = (decide or _default_decide)(state, None, processor="walter-context-preflight",
                                        privacy_class=body.get("privacy_class") or "cloud_allowed",
                                        models=chain, purpose=f"walter-context reassess {kind}", budget="recurring",
                                        timeout=cfg["reassess_timeout_s"], samples=1, occasion="turn", focus="new_message",
                                        facts=facts, ask=ask)
    except Exception as exc:  # noqa: BLE001 — never block the run: said, not memoised (a retry may succeed)
        out.update(reason=f"décision indisponible ({type(exc).__name__}) : l'état est inchangé",
                   text=f"Réévaluation ({kind}) : décision indisponible, poursuivre sur l'état actuel.")
        return out
    d = _decisions(res)
    from .preflight import resolution_brief
    rb = resolution_brief(res)
    if rb:
        out["resolution"] = rb
    out.update(asked=True, reason=reason, decisions=d, signals_asked=ask, model=res.get("model"),
               ms=round((time.perf_counter() - t0) * 1000), text=render(kind, reason, d, ds))
    if kind == "failure":
        w = _norm(trigger.get("where") or trigger.get("tool")) + "|" + _norm(trigger.get("error"))[:120]
        _mark(mgr, sid, "reassessed_failures", w)
    elif kind == "objective.changed":
        _mark(mgr, sid, "reassessed_objective", _norm(trigger.get("goal") or trigger.get("text")) or
              next((_norm(o["text"]) for o in st["objectives"] if o.get("status") == "active"), ""))
    _remember(key, out)
    return out


def _mark(mgr, sid: str, field: str, value: str) -> None:
    """Remember what was assessed in the state's operation block (persisted, so a restart does not re-ask)."""
    with mgr._slock(sid), mgr.store.lock(sid):
        st = mgr.store.load(sid) or mgr.cache.get(sid)
        if not st:
            return
        op = st["operation"]
        if field == "reassessed_failures":
            op[field] = (op.get(field, []) + [value])[-20:]
        else:
            op[field] = value
        mgr.store.save(st)
        mgr.cache[sid] = st


def _remember(key: str, out: dict) -> None:
    with _LOCK:
        _MEMO[key] = {k: v for k, v in out.items() if k not in ("memoized",)}
        while len(_MEMO) > state_settings()["reassess_cache"]:
            _MEMO.popitem(last=False)
