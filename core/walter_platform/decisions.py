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
    out, sources, problems = [], [], []
    for m in compiled["modules"]:
        path = m.get("decisions")
        if not path:
            continue
        try:
            sigs = read(Path(root) / str(path).lstrip("/"), m["id"])
        except (OSError, ValueError) as exc:
            problems.append({"module": m["id"], "path": path, "error": str(exc)[:200]})
            continue
        sources.append({"module": m["id"], "path": path, "signals": len(sigs)})
        out += sigs
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    if occasion:
        out = [s for s in out if occasion in s["occasions"]]
    return {"version": 1, "hash": digest, "signals": out, "sources": sources, "problems": problems}
