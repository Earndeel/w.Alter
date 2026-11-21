"""DecisionState — what a decision is made on, with its epistemic status (2026-11-17).

A decision (the preflight's turn plan, a reassessment during a run) used to read the owner's message and a few thread
cards. The DecisionState is the one structure it reads now, built per occasion from: the message, the last exchange,
the thread, the active objective, the tasks, recent memory, decisions already taken, the sources, the capabilities
and the session's WorkingState. It keeps apart what a model must not mix:

  observations   verifiable facts (seen by a tool, the system, or written in the message), each with source + freshness
  inferences     claims that are reported, deduced or unverified (a sub-agent's word, Memory's projection, a stale fact)
  knowledge      known | searchable (a source that can answer exists, not asked yet) | not_consulted (a source that
                 matters here was not read this turn) | missing (nothing can answer it, or the reference is unresolved)
  contradictions observed between facts of different sources
  constraints    execution constraints in force (the owner's « ne pas… », « uniquement… », the state's constraints)
  unknowns       what is NOT known, said in words. Never filled in: absent stays absent.

Deterministic and model-free; `use` restricts the inputs (the ablation bench measures what each contributes).
`facts` are the names Walter Decision opens its signals with (`when`), `compact()` is what the model reads.
"""
from __future__ import annotations

import re
import time

from .longtext import flags, represent

VERSION = 1
INPUTS = ("message", "last_exchange", "thread", "objective", "tasks", "memory", "prior_decisions", "sources",
          "capabilities")
# What the turn decision reads. Ablation bench 2026-11-17 (bench/decision_state_ablation.py, 21 cases, two runs):
# every input but the capability list scores best (0.683 / 0.603 against 0.635 / 0.571 with it, the message alone
# 0.571 / 0.540) and the list alone costs ~1.5 s of p50. The capabilities stay in the state for the other occasions.
TURN_INPUTS = tuple(i for i in INPUTS if i != "capabilities")

# What a message says it needs → the capability that could answer it. Cues only open a question: they never decide.
NEEDS = (("memory", re.compile(r"(?i)\b(tu te souviens|souviens|rappelle[- ]?toi|la derni[èe]re fois|comme (avant|d['’]habitude)|"
                               r"on avait|on a (d[ée]cid|dit|parl)|j['’]avais|d[ée]cid[ée]|hier|l['’]autre jour|"
                               r"last time|remember|as before|we (decided|said|agreed)|earlier|previously)\b")),
         ("web", re.compile(r"(?i)\b(prix|cours|m[ée]t[ée]o|actualit[ée]s?|news|derni[èe]re version|latest|current|"
                            r"aujourd['’]hui sur|price|weather|release|documentation officielle)\b")),
         ("files", re.compile(r"(?i)(\s|^)(/[\w.-]+){2,}|\b(le fichier|ce fichier|le repo|le dépôt|the file|the repo|"
                              r"le dossier|the directory)\b")),
         ("browser", re.compile(r"(?i)\b(connecte[- ]toi|sur (mon compte|le site)|log ?in|sign in|clique|remplis le formulaire)\b")),
         ("secrets", re.compile(r"(?i)\b(mot de passe|cl[ée] api|api key|token|password|identifiants?|credentials?)\b")))
DEICTIC = re.compile(r"(?i)\b(ça|ceci|cela|celui[- ]ci|celle[- ]ci|le même|la même|ce truc|that|this one|it|them|the same)\b")
TOOL_SOURCE = (("memory", re.compile(r"(?i)memory|recall|mem_|person_lookup|vault")),
               ("web", re.compile(r"(?i)web|search|fetch|browse|http")),
               ("files", re.compile(r"(?i)read|grep|glob|bash|ls\b|cat\b|file")),
               ("browser", re.compile(r"(?i)browser|chrome|camoufox|click")),
               ("secrets", re.compile(r"(?i)secret|bitwarden|vault_get")))
REFERRING = ("memory", "web", "files", "browser", "secrets")
MAX_FACTS = 6


def _age(at: str | None, now: float) -> float | None:
    from .state import _ts
    t = _ts(at)
    return None if t is None else max(now - t, 0.0)


def _short(text, n=200) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


def _row(x: dict, now: float) -> dict:
    return {"fact": _short(x.get("text") or x.get("fact")), "source": (x.get("source") or {}).get("type") or x.get("source_type"),
            "source_id": (x.get("source") or {}).get("id"), "observed_at": x.get("observed_at"),
            "age_s": None if _age(x.get("observed_at"), now) is None else round(_age(x.get("observed_at"), now)),
            "fresh": not x.get("stale"), "verification": x.get("verification", "unverified")}


def build(message: str, *, previous: dict | None = None, thread: dict | None = None, objective: str | dict | None = None,
          tasks: list | None = None, memory: list | None = None, prior_decisions: list | None = None,
          sources: list | None = None, capabilities: list | None = None, working: dict | None = None,
          occasion: str = "turn", use=None, now: float | None = None, trigger: dict | None = None) -> dict:
    """Build the DecisionState. Every input is optional; an input not in `use` is ignored (ablation) and counted
    absent. `working` (a WorkingState) fills what the explicit inputs do not give."""
    now = now if now is not None else time.time()
    use = set(INPUTS) if use is None else set(use)
    absent = [i for i in INPUTS if i not in use]
    w = working or {}
    ds: dict = {"version": VERSION, "occasion": occasion, "inputs": {}, "observations": [], "inferences": [],
                "contradictions": [], "constraints": [], "decisions": [], "tasks": [], "capabilities": [],
                "knowledge": {"known": [], "searchable": [], "not_consulted": [], "missing": []}, "unknowns": []}

    # message ─────────────────────────────────────────────────────────────────────────────────────────────────────
    msg = ""
    if "message" in use:
        rep = represent(message, 1500)
        msg = message or ""
        ds["message"] = {"text": rep.text, "length": rep.length, "truncated": rep.truncated,
                         "flags": sorted({f for s in re.split(r"(?<=[.!?…])\s+|\n+", msg) for f in flags(s)})}
        for s in re.split(r"(?<=[.!?…;])\s+|\n+", msg):
            from .longtext import binding
            if binding(s) and len(ds["constraints"]) < MAX_FACTS and len(s.strip()) > 6:
                ds["constraints"].append({"text": _short(s, 220), "source": "message", "verification": "reported"})
        for kind in ("date", "montant"):
            from .longtext import KINDS
            found = [m.group(0).strip() for p in KINDS[kind][1] for m in p.finditer(msg)][:3]
            for f in found:
                ds["observations"].append({"fact": f"le message écrit « {_short(f, 60)} » ({kind}, valeur non résolue)",
                                           "source": "message", "fresh": True, "verification": "observed"})
    else:
        ds["message"] = {"text": "", "length": 0, "truncated": False, "flags": []}

    # last exchange ───────────────────────────────────────────────────────────────────────────────────────────────
    if "last_exchange" in use and previous and (previous.get("message") or previous.get("answer")):
        age = previous.get("age_s")
        ds["last_exchange"] = {"owner": _short(previous.get("message"), 300), "assistant": _short(previous.get("answer"), 400),
                               "minutes_ago": None if age is None else round(age / 60, 1), "thread": previous.get("thread_id")}
        if previous.get("answer"):      # the assistant's own earlier answer is a claim, not a checked fact
            ds["inferences"].append({"claim": _short(previous["answer"], 200), "basis": "réponse précédente de l'assistant",
                                     "verification": "reported"})

    # thread / objective / tasks / decisions / memory / sources / capabilities ────────────────────────────────────
    if "thread" in use and thread:
        ds["thread"] = {k: _short(thread.get(k), 200) for k in ("id", "title", "objective", "state", "last_message")
                        if thread.get(k)}
        ds["inferences"].append({"claim": f"fil probable : {_short(thread.get('title') or thread.get('id'), 80)}",
                                 "basis": "vues de la mémoire", "verification": "reported"})
        if thread.get("task") or thread.get("kind") == "task":
            ds["tasks"].append({"text": _short(thread.get("task") or thread.get("title"), 160), "status": "open",
                                "source": "thread"})
    obj = None
    if "objective" in use:
        o = objective if objective is not None else next((x for x in w.get("objectives", []) if x.get("status") == "active"), None)
        if isinstance(o, dict):
            obj = {"text": _short(o.get("text") or o.get("goal")), "verification": o.get("verification", "reported"),
                   "source": (o.get("source") or {}).get("type", "memory") if isinstance(o.get("source"), dict) else "memory"}
        elif o:
            obj = {"text": _short(o), "verification": "reported", "source": "memory"}
        if obj and obj["text"]:
            ds["objective"] = obj
    if "tasks" in use:
        rows = tasks if tasks is not None else w.get("tasks", [])
        for t in rows:
            t = {"text": t} if isinstance(t, str) else t
            ds["tasks"].append({"text": _short(t.get("text") or t.get("goal")), "status": t.get("status", "open"),
                                "source": t.get("task_kind") or "task", "result": _short(t.get("result"), 120) or None})
    if "prior_decisions" in use:
        rows = prior_decisions if prior_decisions is not None else w.get("decisions", [])
        for d in rows[:MAX_FACTS * 2]:
            d = {"text": d} if isinstance(d, str) else d
            ds["decisions"].append({"text": _short(d.get("text")), "verification": d.get("verification", "reported"),
                                    "source": (d.get("source") or {}).get("type", "memory") if isinstance(d.get("source"), dict) else "memory"})
    if "memory" in use:
        rows = memory if memory is not None else [x for s in ("information", "constraints", "decisions") for x in w.get(s, [])
                                                  if (x.get("source") or {}).get("type") == "memory"]
        for m in rows[:MAX_FACTS * 2]:
            m = {"text": m} if isinstance(m, str) else m
            ds["inferences"].append({"claim": _short(m.get("text")), "basis": "mémoire" + (" (périmée)" if m.get("stale") else ""),
                                     "verification": "unverified" if m.get("stale") else "reported",
                                     "observed_at": m.get("observed_at")})
    if "sources" in use:
        rows = sources if sources is not None else [x["text"] for x in w.get("sources", [])]
        ds["sources"] = [_short(s if isinstance(s, str) else s.get("text"), 120) for s in rows[:MAX_FACTS * 2]]
    caps = None
    if "capabilities" in use:
        caps = capabilities if capabilities is not None else [x["text"] for x in w.get("capabilities", [])] or None
        if caps is not None:
            ds["capabilities"] = [str(c) for c in caps]

    # the WorkingState's own facts: observed vs inferred, contradictions, constraints ─────────────────────────────
    if w and "tasks" in use or w and "memory" in use:
        for x in w.get("observations", []):
            row = _row(x, now)
            (ds["observations"] if x.get("verification") == "observed" and not x.get("stale") else ds["inferences"]).append(
                row if x.get("verification") == "observed" and not x.get("stale") else
                {"claim": row["fact"], "basis": f"{row['source']}{' (périmé)' if x.get('stale') else ''}",
                 "verification": "unverified" if x.get("stale") else x.get("verification", "inferred"), "observed_at": x.get("observed_at")})
        for x in w.get("information", []):
            ds["inferences"].append({"claim": _short(x.get("text")), "basis": (x.get("source") or {}).get("type", "?") +
                                     (" (périmé)" if x.get("stale") else ""), "verification": "unverified" if x.get("stale")
                                     else x.get("verification", "reported"), "observed_at": x.get("observed_at")})
        ds["contradictions"] += [{"text": _short(x.get("text")), "between": x.get("between")} for x in w.get("contradictions", [])]
        ds["constraints"] += [{"text": _short(x.get("text")), "source": (x.get("source") or {}).get("type"),
                               "verification": x.get("verification", "reported")} for x in w.get("constraints", [])
                              if not any(_short(x.get("text")) == c["text"] for c in ds["constraints"])]
        for x in w.get("pending", []):
            ds["knowledge"]["not_consulted"].append(f"à traiter : {_short(x.get('text'), 120)}")
        op = w.get("operation") or {}
        if op.get("memory_dirty"):
            ds["knowledge"]["not_consulted"].append("la mémoire a changé : sa projection dans l'état est à relire")
        if op.get("interrupted"):
            ds["observations"].append({"fact": "la session a été interrompue", "source": "system", "fresh": True,
                                       "verification": "observed"})
        if op.get("failures"):
            ds["observations"].append({"fact": f"{op['failures']} échec(s) dans cette session", "source": "system",
                                       "fresh": True, "verification": "observed"})
    if trigger:
        ds["trigger"] = {k: _short(v, 200) if isinstance(v, str) else v for k, v in trigger.items()
                         if k in ("kind", "text", "where", "error", "alternative", "details")}

    # known / searchable / not consulted / missing ────────────────────────────────────────────────────────────────
    k = ds["knowledge"]
    consulted = set()
    for x in w.get("observations", []):
        if (x.get("source") or {}).get("type") == "tool" and not x.get("stale"):
            consulted |= {s for s, rx in TOOL_SOURCE if rx.search(x.get("tool") or x.get("text") or "")}
    if any((x.get("source") or {}).get("type") == "memory" and not x.get("stale")
           for s in ("information", "constraints", "decisions", "objectives") for x in w.get(s, [])):
        consulted.add("memory")
    if memory and "memory" in use:
        consulted.add("memory")
    k["known"] = ([f"observé : {o['fact']}" for o in ds["observations"] if o["verification"] == "observed" and o.get("fresh")][:MAX_FACTS]
                  + ([f"objectif : {ds['objective']['text']}"] if ds.get("objective") else [])
                  + [f"décidé : {d['text']}" for d in ds["decisions"]][:MAX_FACTS])
    needs = [(src, rx) for src, rx in NEEDS if rx.search(msg)] if "message" in use else []
    for src, rx in needs:
        m = rx.search(msg)
        label = f"{src} (« {_short(m.group(0), 40)} »)"
        if caps is None and "capabilities" not in use:
            ds["unknowns"].append(f"sources disponibles pour {src} : non indiquées")
        elif caps is not None and src not in caps and not (src == "files" and "tools" in caps):
            k["missing"].append(f"{src} : le message en a besoin, aucune capacité {src} n'est disponible")
        elif src in consulted:
            k["known"].append(f"{src} déjà consulté dans cette session")
        elif src == "memory" and ds["decisions"]:
            k["searchable"].append(f"{label} : des décisions sont dans l'état, la mémoire peut préciser le reste")
            k["not_consulted"].append(src)
        else:
            k["searchable"].append(f"{label} : une source peut répondre, pas encore consultée")
            k["not_consulted"].append(src)
    if "message" in use and len(re.findall(r"\w+", msg)) <= 9 and DEICTIC.search(msg):
        have = any(ds.get(x) for x in ("last_exchange", "thread", "objective")) or ds["tasks"]
        if not have:
            k["missing"].append("référence du message (« ça », « le même »…) : ni échange précédent, ni fil, ni objectif pour la résoudre")
    k["not_consulted"] = list(dict.fromkeys(k["not_consulted"]))
    if "message" not in use:
        ds["unknowns"].append("le message n'est pas fourni")
    if not any(ds.get(x) for x in ("last_exchange", "thread", "objective")) and "message" in use:
        ds["unknowns"].append("aucun contexte (échange, fil ou objectif) : la portée du message est inconnue")
    ds["unknowns"] += [f"manquant : {m}" for m in k["missing"]]
    ds["unknowns"] = list(dict.fromkeys(ds["unknowns"]))
    ds["inputs"] = {"used": [i for i in INPUTS if i in use], "absent": absent, "working_state": bool(w)}
    ds["facts"] = facts(ds)
    return ds


def facts(ds: dict) -> list[str]:
    """The names Walter Decision opens its signals with (`when`). The first two are the preflight's long-standing
    ones; the others describe the state and open nothing today (a module declares a signal with `when` to use them)."""
    out = []
    if ds.get("thread") or ds.get("last_exchange"):
        out.append("threads")
    if any(t.get("status") in ("open", "running", "pending", "interrupted", "waiting") for t in ds["tasks"]):
        out.append("open_task")
    for name, cond in (("has_objective", ds.get("objective")), ("contradiction", ds["contradictions"]),
                       ("unknown_needed", ds["knowledge"]["missing"] or ds["knowledge"]["searchable"]),
                       ("long_message", ds["message"].get("truncated"))):
        if cond:
            out.append(name)
    return out


def compact(ds: dict, max_chars: int = 1400) -> dict:
    """What the decision model reads: the same structure, bounded, every list capped, nothing invented. The order of
    cutting: observations, inferences, then the rest; contradictions, constraints and unknowns are cut last."""
    def cut(rows, n):
        return rows[:n] if len(rows) <= n else rows[:n] + [f"(+{len(rows) - n} autres)"]
    out = {"about": ("Ce que l'assistant a déjà sous les yeux : known, decisions_taken, objective, tasks, last_exchange ne "
                     "demandent aucune recherche. searchable = une source peut répondre, pas encore consultée ; "
                     "missing / unknown = inconnu, à ne pas supposer."),
           "message_flags": ds["message"].get("flags"), "message_length": ds["message"].get("length"),
           **({"objective": ds["objective"]["text"]} if ds.get("objective") else {}),
           **({"last_exchange": ds["last_exchange"]} if ds.get("last_exchange") else {}),
           **({"thread": ds["thread"]} if ds.get("thread") else {}),
           "observed": cut([f"{o['fact']} [{o.get('source')}{'' if o.get('fresh', True) else ', périmé'}]"
                            for o in ds["observations"]], 6),
           "inferred": cut([f"{i['claim']} [{i['verification']}: {i['basis']}]" for i in ds["inferences"]], 6),
           "known": cut(ds["knowledge"]["known"], 5), "searchable": cut(ds["knowledge"]["searchable"], 4),
           "not_consulted": cut(ds["knowledge"]["not_consulted"], 4), "missing": cut(ds["knowledge"]["missing"], 4),
           "contradictions": cut([c["text"] for c in ds["contradictions"]], 4),
           "constraints": cut([c["text"] for c in ds["constraints"]], 6),
           "decisions_taken": cut([d["text"] for d in ds["decisions"]], 5),
           "tasks": cut([f"[{t['status']}] {t['text']}" for t in ds["tasks"]], 5),
           "capabilities": ds["capabilities"], "unknown": cut(ds["unknowns"], 5)}
    out = {k: v for k, v in out.items() if v not in (None, [], {}, "")}
    for key in ("observed", "inferred", "known", "decisions_taken", "tasks", "searchable", "constraints"):
        while len(str(out)) > max_chars and out.get(key) and len(out[key]) > 1:
            out[key] = out[key][:-1]
    return out


def summary(ds: dict) -> dict:
    """The few lines the ContextPlan carries (plan.decision["decision_state"]): counts and the open questions."""
    k = ds["knowledge"]
    return {"inputs": ds["inputs"]["used"], "working_state": ds["inputs"]["working_state"],
            "observed": len([o for o in ds["observations"] if o["verification"] == "observed"]),
            "inferred": len(ds["inferences"]), "contradictions": len(ds["contradictions"]),
            "constraints": len(ds["constraints"]), "searchable": len(k["searchable"]), "not_consulted": len(k["not_consulted"]),
            "missing": k["missing"][:3], "unknown": ds["unknowns"][:3], "long_message": bool(ds["message"].get("truncated"))}
