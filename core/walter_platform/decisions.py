"""Decision signals declared by the modules (Walter Decision 2.0, 2026-11-17).

A module that needs a quick typed judgement or a value read from an incoming event declares it once, in its own
folder (contract key `decisions` → a JSON file, usually `manifest/decisions.json`), as a *signal*: one atomic
question in Walter Decision's language, the occasions it matters on, the facts that make it relevant, the layer it
belongs to (an `observation` read from the input, checkable against it; an `inference` the model judges) and what
consumes it (`use`, `consumers`). Core only discovers and checks the envelope; the question itself belongs to Walter
Decision's language (cognition/router/llm/decision.py checks it when it composes a decision) and the answer to the
module that declared it. A new module benefits from the preflight by declaring a signal: nothing in Context, Router
or Core is edited.

    {"version": 1, "signals": {"<name>": {
        "occasions": ["turn" | "incoming" | "outgoing" | "document" | "result", ...],
        "layer": "observation" | "inference",
        "question": {"type": ..., ...},          # Walter Decision's language
        "when": ["fact", "!fact", "a|b"],         # every term holds; a term is a fact, its negation or a choice of them
        "options_from": "<set>",                  # criteria the caller provides at decision time (e.g. its threads)
        "required": false,                        # true: the decision fails rather than go without it
        "use": "what reads it and what it changes",
        "consumers": ["<module>.<part>"],
        "since": "YYYY-MM-DD"}}}

Relations (Decision Resolver, 2026-11-17). Beside its signals a module may declare how answers relate — its own and
other modules' signals, by global id — so that the answers of one decision are resolved deterministically before
anyone acts on them (cognition/router/llm/resolver.py applies them; no model, no second orchestrator):

    "relations": {"<name>": {
        "type": "implies" | "excludes" | "depends",
        "if":   <condition>,        # implies / excludes: the first side
        "then": <condition>,        # implies: what must also hold; excludes: what cannot hold with `if`
        "signal": "<id>", "on": <condition>,   # depends: the answer of `signal` only counts when `on` holds
        "prefer": "if" | "then" | "none",       # who wins a real conflict (none: reported, nothing changed)
        "strict": false,            # true: `prefer` wins even when it is the less sure side (a bench-validated rule)
        "use": "why the relation holds", "since": "YYYY-MM-DD"}}
    <condition> = {"signal": "<id>", "is" | "in" | "has" | "has_any" | "above" | "below": …} | {"fact": "name" | "!name"}
    (`has_any` [options], 18/11: a several-options answer holds at least one of them)

The global id of a signal is `<module>.<name>`. `collect()` compiles the contracts afresh (never the registry file,
which may lag behind them) and keeps every valid module's signals: one invalid file is reported in `problems` and
left out, it never takes the others down.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import contracts

OCCASIONS = ("turn", "incoming", "outgoing", "document", "result")
LAYERS = ("observation", "inference")
KEYS = {"occasions", "layer", "question", "when", "options_from", "required", "use", "consumers", "since"}
NAME = re.compile(r"[a-z][a-z0-9_]{0,40}\Z")
FACT = re.compile(r"!?[a-z][a-z0-9_.:-]{0,63}\Z")
CONSUMER = re.compile(r"[a-z][a-z0-9-]{0,63}(\.[a-z0-9_.-]{1,64})?\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
MAX_SIGNALS = 32          # per module: a module that needs more questions than that asks them itself
MAX_RELATIONS = 32
REL_KEYS = {"type", "if", "then", "signal", "on", "prefer", "strict", "use", "since"}
REL_TYPES = ("implies", "excludes", "depends")
GLOBAL_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\.[a-z][a-z0-9_]{0,40}\Z")
TESTS = {"is": str, "in": list, "has": str, "has_any": list, "above": (int, float), "below": (int, float)}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def check_signal(name: str, s) -> dict:
    """The envelope of one declared signal (the question's own language is Walter Decision's)."""
    _require(isinstance(name, str) and NAME.fullmatch(name), f"signal name {str(name)[:40]!r}: a-z, 0-9, _ (41 at most)")
    _require(isinstance(s, dict) and set(s) <= KEYS, f"signal {name}: unknown keys {sorted(set(s or {}) - KEYS)}")
    occ = s.get("occasions")
    _require(isinstance(occ, list) and occ and set(occ) <= set(OCCASIONS) and len(occ) == len(set(occ)),
             f"signal {name}: occasions among {', '.join(OCCASIONS)}")
    _require(s.get("layer") in LAYERS, f"signal {name}: layer is observation or inference")
    q = s.get("question")
    _require(isinstance(q, dict) and isinstance(q.get("type"), str), f"signal {name}: question in Walter Decision's language")
    when = s.get("when", [])
    _require(isinstance(when, list) and all(isinstance(t, str) and all(FACT.fullmatch(p) for p in t.split("|"))
                                             for t in when), f"signal {name}: when = facts, !fact, a|b")
    if "options_from" in s:
        _require(isinstance(s["options_from"], str) and NAME.fullmatch(s["options_from"]),
                 f"signal {name}: options_from names a set")
        _require(q.get("type") == "choice", f"signal {name}: options_from goes with a choice")
    _require(isinstance(s.get("required", False), bool), f"signal {name}: required is true or false")
    _require(isinstance(s.get("use"), str) and len(s["use"].strip()) >= 8, f"signal {name}: use says what consumes it")
    cons = s.get("consumers", [])
    _require(isinstance(cons, list) and all(isinstance(c, str) and CONSUMER.fullmatch(c) for c in cons),
             f"signal {name}: consumers are <module>.<part>")
    if "since" in s:
        _require(isinstance(s["since"], str) and DATE.fullmatch(s["since"]), f"signal {name}: since is YYYY-MM-DD")
    return s


def check_condition(where: str, c) -> dict:
    _require(isinstance(c, dict), f"{where}: a condition is an object")
    if "fact" in c:
        _require(set(c) == {"fact"} and isinstance(c["fact"], str) and FACT.fullmatch(c["fact"]),
                 f"{where}: {{fact: name | !name}}")
        return c
    tests = set(c) - {"signal"}
    _require(isinstance(c.get("signal"), str) and GLOBAL_ID.fullmatch(c["signal"]), f"{where}: signal = <module>.<name>")
    _require(len(tests) == 1 and tests <= set(TESTS), f"{where}: one test among {', '.join(TESTS)}")
    t = tests.pop()
    v = c[t]
    _require(isinstance(v, TESTS[t]) and not isinstance(v, bool), f"{where}: {t} has the wrong type")
    if t in ("in", "has_any"):
        _require(v and all(isinstance(x, str) for x in v), f"{where}: {t} = a non-empty list of options")
    if t in ("above", "below"):
        _require(0 <= float(v) <= 1, f"{where}: {t} is a probability")
    return c


def check_relation(name: str, r) -> dict:
    """The envelope of one declared relation between answers (applied by Walter Decision's resolver)."""
    _require(isinstance(name, str) and NAME.fullmatch(name), f"relation name {str(name)[:40]!r}: a-z, 0-9, _")
    _require(isinstance(r, dict) and set(r) <= REL_KEYS, f"relation {name}: unknown keys {sorted(set(r or {}) - REL_KEYS)}")
    _require(r.get("type") in REL_TYPES, f"relation {name}: type among {', '.join(REL_TYPES)}")
    if r["type"] == "depends":
        _require(isinstance(r.get("signal"), str) and GLOBAL_ID.fullmatch(r["signal"]), f"relation {name}: signal = <module>.<name>")
        check_condition(f"relation {name}.on", r.get("on"))
        _require("if" not in r and "then" not in r, f"relation {name}: depends takes signal + on")
    else:
        check_condition(f"relation {name}.if", r.get("if"))
        check_condition(f"relation {name}.then", r.get("then"))
        _require(r.get("prefer", "none") in ("if", "then", "none"), f"relation {name}: prefer is if, then or none")
        _require(not ("fact" in r["then"] and r.get("prefer") == "if" and r["type"] == "implies"),
                 f"relation {name}: a fact cannot be changed (prefer then, or none)")
    _require(isinstance(r.get("strict", False), bool), f"relation {name}: strict is true or false")
    _require(isinstance(r.get("use"), str) and len(r["use"].strip()) >= 8, f"relation {name}: use says why it holds")
    if "since" in r:
        _require(isinstance(r["since"], str) and DATE.fullmatch(r["since"]), f"relation {name}: since is YYYY-MM-DD")
    return r


def read_relations(path, module: str) -> list[dict]:
    """One module's declared relations (an absent key = none), checked, with their global ids."""
    doc = json.loads(Path(path).read_text())
    rel = doc.get("relations", {})
    _require(isinstance(rel, dict) and len(rel) <= MAX_RELATIONS, f"relations: 0..{MAX_RELATIONS} per module")
    return [{"id": f"{module}.{name}", "module": module, **check_relation(name, r)} for name, r in rel.items()]


def read(path, module: str) -> list[dict]:
    """One module's declared signals, checked, with their global ids."""
    p = Path(path)
    _require(p.stat().st_size <= 256 * 1024, "oversized signals file")
    try:
        doc = json.loads(p.read_text())
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("invalid signals JSON") from None
    _require(isinstance(doc, dict) and doc.get("version") == 1, "signals file: {version: 1, signals: {...}}")
    sig = doc.get("signals")
    _require(isinstance(sig, dict) and 0 < len(sig) <= MAX_SIGNALS, f"signals: 1..{MAX_SIGNALS} per module")
    return [{"id": f"{module}.{name}", "module": module, "name": name, **check_signal(name, s)}
            for name, s in sig.items()]


def collect(catalog=None, *, root="/", occasion: str | None = None) -> dict:
    """Every module's declared signals → {version, hash, signals, sources, problems}. `hash` identifies the whole
    set (Walter Decision keys its compiled schemas and its journal on it)."""
    compiled = contracts.compile_registry(catalog, root=root)
    out, relations, sources, problems = [], [], [], []
    for m in compiled["modules"]:
        path = m.get("decisions")
        if not path:
            continue
        try:
            sigs = read(Path(root) / str(path).lstrip("/"), m["id"])
        except (OSError, ValueError) as exc:
            problems.append({"module": m["id"], "path": path, "error": str(exc)[:200]})
            continue
        try:                                # a bad relation drops the module's relations, never its signals
            rels = read_relations(Path(root) / str(path).lstrip("/"), m["id"])
        except (OSError, ValueError) as exc:
            problems.append({"module": m["id"], "path": path, "error": f"relations: {str(exc)[:180]}"})
            rels = []
        sources.append({"module": m["id"], "path": path, "signals": len(sigs), "relations": len(rels)})
        out += sigs
        relations += rels
    ids = {s["id"] for s in out}
    for r in list(relations):               # a relation naming an undeclared signal is reported and left out
        named = {c.get("signal") for c in (r.get("if"), r.get("then"), r.get("on")) if isinstance(c, dict)} | {r.get("signal")}
        unknown = sorted(n for n in named if n and n not in ids)
        if unknown:
            problems.append({"module": r["module"], "relation": r["id"], "error": "unknown signals " + ", ".join(unknown)})
            relations.remove(r)
    digest = hashlib.sha256(json.dumps([out, relations], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16] \
        if relations else hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    if occasion:
        out = [s for s in out if occasion in s["occasions"]]
    return {"version": 1, "hash": digest, "signals": out, "relations": relations, "sources": sources,
            "problems": problems}
