"""Walter Decision — the Decision Resolver (2026-11-17, mission « Native Engine × Cognitive Architecture » §6).

A decision composed from several modules' signals comes back as independent answers. Before a module acts on them
they are resolved here, deterministically and without a model, against the relations the modules declare beside
their signals (Core: `walter decisions` → `relations`, envelope in walter_platform/decisions.py):

  implies   `if` holds → `then` must hold            (« memory needed » → the plan carries the owner's memory)
  excludes  `if` and `then` cannot both hold          (« a new subject » and « carry on the open task »)
  depends   `signal` only counts when `on` holds      (« extensive search » means nothing without a thread to search)

For every broken relation the resolver tells a real conflict (both sides sure: confidence ≥ floor, or a fact) from
an uncertainty (one side unsure: the less sure side yields, unless the relation is `strict`). A conflict is settled
only by the relation's `prefer`; `prefer: none` only reports (conflict or uncertainty), nothing is changed — the
consumer sees it and the model decides. A
deterministic fact (the caller's or a cue) is certain and never changed. Every change keeps its provenance (what the
model said, which relation changed it and why). What a relation needed but no model answered is `missing`, said, never
guessed; an unanswered required signal too.

The resolver informs: it never calls a model, never asks again, never orders an action. Context keeps the preflight
(it reads `resolution.signals` where it read `signals`), the Router keeps the choice of models, the Engine keeps the
execution.

    resolve(answers_by_signal, relations, facts=(), *, floor=0.6, required=(), asked=None) -> resolution
"""
from __future__ import annotations

import copy

FLOOR = 0.6            # below it an answer is « uncertain » (Walter Decision's calibration: choice confidence / noul distance)
HAS_MIN = 0.5          # a several-options answer « has » an option at this probability (the consumers' NEED_MIN)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _conf(a) -> float | None:
    from decision import confidence
    return confidence(a)


def _probs(a: dict) -> dict:
    p = a.get("probabilities")
    return p if isinstance(p, dict) else {}


def evaluate(cond: dict, answers: dict, facts: set) -> tuple[bool | None, float | None]:
    """→ (holds, how sure). None = no answer to judge it on (unanswered, unavailable, set aside)."""
    if "fact" in cond:
        f = cond["fact"]
        return ((f[1:] not in facts) if f.startswith("!") else (f in facts)), 1.0
    a = answers.get(cond["signal"])
    if not isinstance(a, dict):
        return None, None
    if "is" in cond or "in" in cond:
        c = a.get("choice")
        if c is None:
            return None, None
        want = [cond["is"]] if "is" in cond else cond["in"]
        return c in want, _conf(a)
    if "has_any" in cond:                  # at least one of the options (18/11)
        got = [evaluate({"signal": cond["signal"], "has": o}, answers, facts) for o in cond["has_any"]]
        known = [(h, s) for h, s in got if h is not None]
        if not known:
            return None, None
        held = [s for h, s in known if h]
        return (True, max(held)) if held else (False, min(s for _, s in known))
    if "has" in cond:
        opt = cond["has"]
        p = _probs(a).get(opt)
        if _num(p):
            return p >= HAS_MIN, max(float(p), 1 - float(p))
        if isinstance(a.get("choices"), list):
            return opt in a["choices"], _conf(a)
        if a.get("choice") is not None:
            return a["choice"] == opt, _conf(a)
        return None, None
    p = a.get("noul")
    if not _num(p):
        return None, None
    p = float(p)
    return (p >= cond["above"]) if "above" in cond else (p < cond["below"]), max(p, 1 - p)


def _make(cond: dict, answers: dict, hold: bool) -> dict | None:
    """Change the answer of `cond`'s signal so that `cond` holds (or not) → the new answer; None = cannot (a fact,
    or « not this option » of a single choice, which names no other option: the answer is then set aside)."""
    if "fact" in cond:
        return None
    a = copy.deepcopy(answers.get(cond["signal"]) or {})
    if "is" in cond or "in" in cond:
        if not hold:
            return None
        want = [cond["is"]] if "is" in cond else list(cond["in"])
        probs = _probs(a)
        best = max(want, key=lambda o: (probs.get(o) if _num(probs.get(o)) else -1, -want.index(o)))
        a["choice"] = best
        return a
    if "has_any" in cond:                  # « one of them » names no single option to add; « none of them » can
        if hold:
            return None
        for o in cond["has_any"]:
            a = _make({"signal": cond["signal"], "has": o}, {cond["signal"]: a}, False) or a
        return a
    if "has" in cond:
        opt = cond["has"]
        probs = dict(_probs(a))
        chosen = list(a.get("choices") or ([a["choice"]] if a.get("choice") else []))
        if hold:
            chosen = chosen if opt in chosen else [*chosen, opt]
            if _num(probs.get(opt)):
                probs[opt] = max(float(probs[opt]), HAS_MIN)
        else:
            chosen = [c for c in chosen if c != opt]
            if _num(probs.get(opt)):
                probs[opt] = min(float(probs[opt]), round(HAS_MIN - 0.01, 2))
        a["choices"] = chosen
        if probs:
            a["probabilities"] = probs
        return a
    p = float(a.get("noul") or 0.0)
    edge = cond.get("above", cond.get("below"))
    if "above" in cond:
        a["noul"] = max(p, edge) if hold else min(p, round(edge - 0.01, 2))
    else:
        a["noul"] = min(p, round(edge - 0.01, 2)) if hold else max(p, edge)
    return a


def _side(cond: dict) -> str:
    return cond.get("signal") or ("fact " + cond["fact"])


def resolve(answers: dict, relations: list, facts=(), *, floor: float = FLOOR, required=(), asked=None) -> dict:
    """The answers of one decision (by signal id) resolved against the declared relations → {signals, changed,
    conflicts, uncertain, set_aside, missing, applied}. Pure and deterministic; `answers` is not modified."""
    facts = set(facts or ())
    out = {k: copy.deepcopy(v) for k, v in (answers or {}).items()}
    asked = set(out) if asked is None else set(asked)
    changed: dict = {}
    conflicts, uncertain_rel, set_aside, missing, applied = [], [], [], [], []

    def change(sid: str, new: dict | None, rel: dict, why: str):
        if sid not in changed:
            changed[sid] = {"was": copy.deepcopy(out.get(sid)), "by": [], "why": []}
        changed[sid]["by"].append(rel["id"])
        changed[sid]["why"].append(why)
        if new is None:
            out[sid] = None
            set_aside.append({"signal": sid, "relation": rel["id"], "why": why})
        else:
            new["resolved_by"] = rel["id"]
            out[sid] = new

    def relevant(rel) -> bool:              # a relation about signals this decision did not ask is not this decision's
        sides = [c for c in (rel.get("if"), rel.get("then"), rel.get("on")) if isinstance(c, dict)]
        named = {c["signal"] for c in sides if "signal" in c} | ({rel["signal"]} if rel.get("signal") else set())
        return bool(named) and named <= asked

    rules = [r for r in relations or () if r.get("type") in ("implies", "excludes") and relevant(r)]
    reported: set = set()
    for _ in range(4):                       # a change can break or settle another relation: until stable
        progress, missing = False, []
        for rel in rules:
            hi, ci = evaluate(rel["if"], out, facts)
            ht, ct = evaluate(rel["then"], out, facts)
            broken = (hi is True and ht is False) if rel["type"] == "implies" else (hi is True and ht is True)
            if hi is True and ht is None and rel["type"] == "implies":
                if "fact" in rel["if"] and rel.get("prefer") == "if" and "signal" in rel["then"]:
                    new = _make(rel["then"], out, True)     # a certain fact fills what no model answered
                    if new is not None:
                        change(rel["then"]["signal"], new, rel, f"{_side(rel['if'])} (certain) ; aucune réponse du modèle")
                        applied.append(rel["id"])
                        progress = True
                        continue
                missing.append({"signal": rel["then"].get("signal") or _side(rel["then"]), "relation": rel["id"],
                                "why": f"{_side(rel['if'])} tient ; rien ne dit si {_side(rel['then'])} suit"})
                continue
            if not broken:
                continue
            applied.append(rel["id"])
            sure = (ci or 0) >= floor and (ct or 0) >= floor
            prefer = rel.get("prefer", "none")
            item = {"relation": rel["id"], "type": rel["type"], "if": _side(rel["if"]), "then": _side(rel["then"]),
                    "confidence": {"if": None if ci is None else round(ci, 3), "then": None if ct is None else round(ct, 3)},
                    "use": rel.get("use", "")}
            # who yields: a sure conflict or a strict rule → `prefer`; an uncertainty → the less sure side
            if prefer == "none" or sure or rel.get("strict"):
                winner = prefer                             # none: the relation only reports, whatever the confidences
            else:
                winner = "if" if (ci or 0) >= (ct or 0) else "then"
                if "fact" in rel["if"]:
                    winner = "if"
                if "fact" in rel["then"]:
                    winner = "then"
            item["settled"] = winner if winner != "none" else None
            if rel["id"] not in reported:
                reported.add(rel["id"])
                (conflicts if sure else uncertain_rel).append(item)
            if winner == "none":
                continue
            loser = rel["then"] if winner == "if" else rel["if"]
            # implies: the `then` side is made to hold, or the `if` side not to; excludes: the loser side not to hold
            hold = rel["type"] == "implies" and winner == "if"
            if "fact" in loser:
                item["settled"] = None                      # a fact is never changed: reported only
                continue
            new = _make(loser, out, hold)
            why = (f"{'conflit' if sure else 'incertitude'} avec {_side(rel[winner])} ({rel['type']}) : "
                   f"{'réglé par la règle' if sure or rel.get('strict') else 'le côté le moins sûr cède'}")
            change(loser["signal"], new, rel, why)
            progress = True
        if not progress:
            break

    for rel in [r for r in relations or () if r.get("type") == "depends" and relevant(r)]:
        if not isinstance(out.get(rel["signal"]), dict):
            continue
        h, _ = evaluate(rel["on"], out, facts)
        if h is False:
            applied.append(rel["id"])
            change(rel["signal"], None, rel, f"ne compte que si {_side(rel['on'])} tient")
        elif h is None:
            missing.append({"signal": _side(rel["on"]), "relation": rel["id"],
                            "why": f"{rel['signal']} en dépend ; pas de réponse pour en juger"})

    unsure = []
    for sid in sorted(asked):
        a = out.get(sid)
        if a is None and sid in set(required) and not any(s["signal"] == sid for s in set_aside):
            missing.append({"signal": sid, "relation": None, "why": "requis, sans réponse"})
            continue
        c = _conf(a) if isinstance(a, dict) else None
        if c is not None and c < floor and sid not in changed:
            unsure.append({"signal": sid, "confidence": round(c, 3)})
    return {"signals": out, "changed": changed, "conflicts": conflicts, "uncertain": unsure,
            "uncertain_relations": uncertain_rel, "set_aside": set_aside, "missing": missing,
            "applied": sorted(set(applied)), "floor": floor}


def brief(res: dict) -> dict:
    """What a consumer journals or shows: counts and names, no answers."""
    return {"changed": {k: v["by"] for k, v in res["changed"].items()},
            **({"conflicts": [c["relation"] for c in res["conflicts"]]} if res["conflicts"] else {}),
            **({"uncertain": [u["signal"] for u in res["uncertain"]]} if res["uncertain"] else {}),
            **({"missing": [m["signal"] for m in res["missing"]]} if res["missing"] else {}),
            **({"set_aside": [s["signal"] for s in res["set_aside"]]} if res["set_aside"] else {})}
