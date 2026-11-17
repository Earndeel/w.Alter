"""Walter Decision (2026-11-16): the typed decision language, the needs registry, reuse and escalation — the layer
between a module that needs a quick typed judgement and the decision APIs the Router picks (structured.decisions).

Language. A decision is a `state` (any JSON the model reads) and named `questions`, each of one type: noul (yes/no
probability), choice (one of named criteria/options, a probability each), score, number, date, text, spans, box,
boxes. A question is written once in this language and sent unchanged to whichever provider answers (OpenRouter
Decisions, Nace and Liquid systemone, Workers AI): the adapters change the transport, never the question.
`compile_questions` checks it before any provider is called (a malformed question costs nothing and says why) and
gives its schema key, the identity of a question set (reuse, calibration, journals).

Needs. A module declares what it asks (config/decision-needs.json: owner, purpose, latency budget, reuse window,
escalation). The caller names its need in the request (`need`, walter_memory.llm.decide sends its processor); an
undeclared need gets the default policy (no reuse, no escalation, the caller's timeout). The registry holds policy only: the Router keeps the choice and order of the
models (its decision chain), Context keeps its preflight questions.

Reuse. The same state and the same questions on the same chain within the need's window get the answer already
given (`reused: true`), without a call: a decision asked again — a retried turn, a warm-up, two consumers of the same
event — is never paid or waited for twice. Window 0 turns it off.

Routes (2026-11-17). The language is Liquid's typed one (d1.2): besides noul/choice/score, `choice` with
`multiple: true` (each option its own probability), `text` / `number` / `date` (a value read from the state, with
its `span` and `found`), `number` with `range` (+ `step`, `unit`: an estimate, median and [p10, p90] `interval`),
`spans` (every passage, `max` ≤ 64), `box` / `boxes` (images), and `media` beside the state (images, audio). What a
route can carry differs and is said once, in `capabilities` (measured by real calls on 17/11; Liquid's own API from
its documentation, untested without a key). `plan` splits a question set for one model: what its decision route
answers natively, what goes to OpenRouter's Extractions route (d1.2 models: values, estimates, passages), what is
emulated (several options = one noul per option, since OpenRouter and Nace silently answer ONE option to
`multiple: true`), and refuses by name what it cannot carry (box, audio outside Liquid's own API) — the chain then
goes on to the next model. `assemble` returns every answer in the one canonical shape (Liquid's).

Escalation (model adapted to difficulty). With `escalate_below` set for a need, the questions the first model
answered with a confidence under that threshold — and only those — are asked again to the next model of the chain;
their answers replace the uncertain ones and the reply says which (`escalated`). Off for every need until a bench
gives the threshold (calibration fields in the journal: `confidence` per question, `schema`, `need`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

TYPES = ("noul", "choice", "score", "number", "date", "text", "spans", "box", "boxes")
MAX_QUESTIONS = 32
MAX_INSTRUCTIONS = 6000
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
NEEDS_FILE = Path(__file__).resolve().parents[1] / "config" / "decision-needs.json"
DEFAULT_POLICY = {"memo_ttl_s": 0, "escalate_below": None, "max_timeout_s": None}   # undeclared: no reuse
MEMO_SIZE = 512


class Invalid(ValueError):
    """A request that is not a decision in Walter's language (the message says which question and why)."""


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(value) -> str:
    return hashlib.sha256(_canon(value).encode()).hexdigest()[:16]


def compile_questions(questions) -> tuple[dict, str]:
    """Check a question set against the language → (the questions, their schema key). Extra fields a provider
    understands are kept as they are; what no provider could answer is refused."""
    if not isinstance(questions, dict) or not questions:
        raise Invalid("questions must be a non-empty object")
    if len(questions) > MAX_QUESTIONS:
        raise Invalid(f"at most {MAX_QUESTIONS} questions per decision")
    for name, q in questions.items():
        if not isinstance(name, str) or not KEY.match(name):
            raise Invalid(f"question name {str(name)[:40]!r}: letters, digits, _ . - (64 at most), a letter first")
        if not isinstance(q, dict):
            raise Invalid(f"question {name}: an object")
        kind = q.get("type")
        if kind not in TYPES:
            raise Invalid(f"question {name}: type must be one of {', '.join(TYPES)}")
        text = q.get("instructions")
        if text is not None and (not isinstance(text, str) or len(text) > MAX_INSTRUCTIONS):
            raise Invalid(f"question {name}: instructions must be text of {MAX_INSTRUCTIONS} characters at most")
        if kind == "choice":
            crit, opts = q.get("criteria"), q.get("options")
            if isinstance(crit, dict) and crit:
                if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in crit.items()):
                    raise Invalid(f"question {name}: criteria map option names to descriptions (text)")
            elif not (isinstance(opts, list) and opts and all(isinstance(o, str) and o for o in opts)):
                raise Invalid(f"question {name}: a choice needs criteria (or options)")
            if "multiple" in q and not isinstance(q["multiple"], bool):
                raise Invalid(f"question {name}: multiple is true or false")
        if kind == "number":
            if "range" in q:
                rng = q["range"]
                if not (isinstance(rng, list) and len(rng) == 2 and all(_num(v) for v in rng) and rng[0] < rng[1]):
                    raise Invalid(f"question {name}: range is [low, high], two numbers, low < high")
                step = q.get("step")
                if step is not None:
                    if not _num(step) or step <= 0:
                        raise Invalid(f"question {name}: step is a positive number")
                    n = (rng[1] - rng[0]) / step
                    if abs(n - round(n)) > 1e-9:
                        raise Invalid(f"question {name}: step must divide high - low")
            elif "step" in q:
                raise Invalid(f"question {name}: step goes with range (an estimate)")
            if "unit" in q and not isinstance(q["unit"], str):
                raise Invalid(f"question {name}: unit is text")
        if kind == "date" and "order" in q and q["order"] not in DATE_ORDERS:
            raise Invalid(f"question {name}: order is one of {', '.join(DATE_ORDERS)}")
        if kind in ("spans", "boxes") and "max" in q:
            if isinstance(q["max"], bool) or not isinstance(q["max"], int) or not 1 <= q["max"] <= 64:
                raise Invalid(f"question {name}: max is an integer 1..64")
    return questions, _digest(questions)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


DATE_ORDERS = ("dmy", "mdy", "ymd")
WALTER_ONLY = ("order",)      # read by Walter, never sent to a provider


def provider_question(q: dict) -> dict:
    return {k: v for k, v in q.items() if k not in WALTER_ONLY} if any(k in q for k in WALTER_ONLY) else q


MEDIA_TYPES = ("image", "audio")
MAX_MEDIA = 8


def check_media(media) -> list:
    """`media` beside the state: [{type: image | audio, data: base64 or a data: URL}], 8 at most (Liquid's limit)."""
    if media is None:
        return []
    if not isinstance(media, list) or len(media) > MAX_MEDIA:
        raise Invalid(f"media is a list of {MAX_MEDIA} items at most")
    for i, m in enumerate(media):
        if not isinstance(m, dict) or m.get("type") not in MEDIA_TYPES or not isinstance(m.get("data"), str) \
                or not m["data"]:
            raise Invalid(f"media {i}: {{type: image | audio, data: base64 or a data: URL}}")
    return media


# ── what each route can answer (17/11/2026) ─────────────────────────────────────────────────────────────────────
# Measured by real calls on 17/11 (scratch probes, DECISIONS.md 2026-11-17): OpenRouter Decisions answers noul /
# choice / score for every decision model and refuses text, number, date, spans, box(es) and audio (400); with
# `multiple: true` it answers ONE option (probabilities summing to 1) — Nace's own API the same. OpenRouter's
# Extractions route answers text / number / date / list / estimate, for d1.2 and d1.2-ultra only (d1-ultra, Drex
# Max: 404). Liquid's own API answers every kind for d1.2 / d1.2-ultra (its documentation; no key yet: untested).
BASE_KINDS = frozenset({"noul", "choice", "score"})
TYPED_KINDS = frozenset({"multiple", "text", "number", "date", "estimate", "spans", "box", "boxes"})
EXTRACTION_KINDS = frozenset({"text", "number", "date", "estimate", "spans"})
LIQUID_TYPED = frozenset({"d1.2", "d1.2-ultra"})
# OpenRouter models whose page lists /api/alpha/extractions (`endpoints` of /api/v1/models, 17/11)
OPENROUTER_EXTRACTIONS = frozenset({"liquid/d1.2", "liquid/d1.2-ultra"})
NOT_FOUND = 0.5        # a value or an option under this probability is absent (Liquid's own threshold)


class Unsupported(ValueError):
    """A question set this model's route cannot carry (the message names each question and its kind)."""


def kind(q: dict) -> str:
    """The kind of a question: its type, `multiple` for a choice of several options, `estimate` for a number with
    a range."""
    t = q.get("type")
    if t == "choice" and q.get("multiple") is True:
        return "multiple"
    if t == "number" and q.get("range") is not None:
        return "estimate"
    return t


def capabilities(provider: str, model: str) -> dict:
    """What a route carries: `native` kinds (its decision call), `extract` kinds (OpenRouter's Extractions route),
    `emulate` kinds (several options as one noul each), `media` kinds; `verified` = measured, not only documented."""
    short = model.split("/", 1)[-1]
    if provider == "liquid":
        typed = short in LIQUID_TYPED
        return {"native": BASE_KINDS | (TYPED_KINDS if typed else frozenset()), "extract": frozenset(),
                "emulate": frozenset() if typed else frozenset({"multiple"}),
                "media": frozenset(MEDIA_TYPES) if typed else frozenset({"image"}), "verified": False}
    if provider == "openrouter":
        return {"native": BASE_KINDS,
                "extract": EXTRACTION_KINDS if model in OPENROUTER_EXTRACTIONS else frozenset(),
                "emulate": frozenset({"multiple"}), "media": frozenset(), "verified": True}
    return {"native": BASE_KINDS, "extract": frozenset(), "emulate": frozenset({"multiple"}), "media": frozenset(),
            "verified": provider == "nace"}


def options(q: dict) -> dict:
    crit = q.get("criteria")
    return dict(crit) if isinstance(crit, dict) and crit else {o: "" for o in q.get("options") or []}


def _option_key(name: str, i: int) -> str:
    return f"{name}.option{i}"


def plan(provider: str, model: str, questions: dict, media=()) -> dict:
    """Split a question set for one model → {native, extract, emulated}; raises Unsupported naming what it cannot
    carry. `emulated` maps a several-options question to its (option, noul key) pairs."""
    cap = capabilities(provider, model)
    refused = [f"media {t}" for t in sorted({m["type"] for m in media or ()} - cap["media"])]
    native, extract, emulated = {}, {}, {}
    for name, q in questions.items():
        k = kind(q)
        if k in cap["native"]:
            native[name] = provider_question(q)
        elif k in cap["extract"]:
            extract[name] = q
        elif k == "multiple" and k in cap["emulate"]:
            ask = (q.get("instructions") or "Which of these options apply?").strip()
            pairs = []
            for i, (opt, desc) in enumerate(options(q).items()):
                sub = _option_key(name, i)
                if sub in questions:
                    raise Invalid(f"question {sub}: name reserved for the options of {name}")
                native[sub] = {"type": "noul", "instructions": f"{ask}\n\nOption « {opt} »"
                               + (f" : {desc}" if desc else "") + "\nDoes this option apply? Several options can apply"
                               " at once, or none."}
                pairs.append((opt, sub))
            emulated[name] = pairs
        else:
            refused.append(f"{name} ({k})")
    if refused:
        raise Unsupported(f"{model} cannot answer " + ", ".join(refused))
    return {"native": native, "extract": extract, "emulated": emulated}


def render_state(state) -> str:
    """The state as text for a text-only route: as Liquid renders a JSON state (2-space indentation), so the
    positions of what is read (`span`) are the same whichever route answered."""
    return state if isinstance(state, str) else json.dumps(state, ensure_ascii=False, indent=2)


def extraction_fields(extract: dict) -> dict:
    """Walter questions → OpenRouter Extractions fields (estimate = number with a range, list of text = spans)."""
    out = {}
    for name, q in extract.items():
        k, f = kind(q), {}
        if q.get("instructions"):
            f["instructions"] = q["instructions"]
        if k == "estimate":
            f.update(type="estimate", min=q["range"][0], max=q["range"][1])
            if q.get("step"):
                f["step"] = q["step"]
        elif k == "spans":
            f.update(type="list", items="text")
        else:
            f.update(type=k, null_threshold=NOT_FOUND)
            if k == "number" and q.get("unit"):
                f["unit"] = q["unit"]
        out[name] = f
    return out


def from_extraction(q: dict, a, text: str):
    """One Extractions answer → the canonical (Liquid) shape."""
    if not isinstance(a, dict):
        return None
    k = kind(q)
    if k == "estimate":
        return {"type": "number", "number": a.get("median", a.get("value")), "interval": [a.get("p10"), a.get("p90")],
                "unit": q.get("unit")}
    if k == "spans":
        vals, spans, conf = a.get("value") or [], a.get("spans") or [], a.get("confidences") or []
        items = [{"text": v, "span": spans[i] if i < len(spans) else None,
                  "found": conf[i] if i < len(conf) else None} for i, v in enumerate(vals)]
        items = items[:q["max"]] if q.get("max") else items
        return {"type": "spans", "spans": items, "count": len(items), "at_least": None}
    pn = a.get("p_null")
    found = round(1 - float(pn), 6) if _num(pn) else None
    span = a.get("span")
    ok = isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span)
    written = text[span[0]:span[1]] if ok else None
    value = a.get("value")
    if k == "text":
        return {"type": "text", "text": value, "span": span if ok else None, "found": found}
    out = {"type": k, k: value, "text": written, "span": span if ok else None, "found": found}
    if k == "number":
        out["unit"] = q.get("unit")
    return out


_NUMERIC_DATE = re.compile(r"^\s*(\d{1,4})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,4})\s*$")


def finish(questions: dict, answers: dict) -> dict:
    """What Walter reads itself, whatever the model: a date the model found but left unread because its written form
    is ambiguous (17/11: « 05/12/2026 » and « 10/11/2026 » found, value null, on d1.2 and d1.2-ultra) is read in the
    order the question declares (`order`: dmy, mdy, ymd). Deterministic; marked `read_by: walter`."""
    import datetime
    out = None
    for name, q in questions.items():
        a = answers.get(name)
        if q.get("type") != "date" or not q.get("order") or not isinstance(a, dict) or a.get("date") is not None \
                or not _num(a.get("found")) or a["found"] < NOT_FOUND:
            continue
        m = _NUMERIC_DATE.match(a.get("text") or "")
        if not m:
            continue
        parts = dict(zip(q["order"], (int(x) for x in m.groups())))
        try:
            day = datetime.date(parts["y"], parts["m"], parts["d"])
        except ValueError:
            continue
        out = out if out is not None else dict(answers)
        out[name] = {**a, "date": day.isoformat(), "read_by": "walter"}
    return answers if out is None else out


def assemble(questions: dict, p: dict, native: dict, extracted: dict, text: str) -> dict:
    """The answers of the parts of a plan, in the order of the questions and in the canonical shape."""
    out = {}
    for name, q in questions.items():
        if name in p["emulated"]:
            probs = {opt: (native.get(sub) or {}).get("noul") for opt, sub in p["emulated"][name]}
            if any(v is None for v in probs.values()):
                continue
            out[name] = {"type": "choice", "choices": [o for o, v in probs.items() if v >= NOT_FOUND],
                         "probabilities": probs, "emulated": "noul"}
        elif name in p["extract"]:
            got = from_extraction(q, extracted.get(name), text)
            if got is not None:
                out[name] = got
        elif name in native:
            out[name] = native[name]
    return out


# ── needs registry ──────────────────────────────────────────────────────────────────────────────────────────────
_needs: dict = {"mtime": None, "data": {}}
_needs_lock = threading.Lock()


def needs() -> dict:
    """Declared needs (re-read when the file changes); {} when there is no registry."""
    try:
        mtime = NEEDS_FILE.stat().st_mtime
    except OSError:
        return {}
    with _needs_lock:
        if _needs["mtime"] != mtime:
            data = json.loads(NEEDS_FILE.read_text())
            _needs["data"] = {k: v for k, v in (data.get("needs") or {}).items() if isinstance(v, dict)}
            _needs["mtime"] = mtime
        return _needs["data"]


def coverage(chain: list[str], provider_of) -> dict:
    """For each declared need: each kind it asks (`types`) or could ask (`new_kinds`) → per model of the chain, how it
    is carried (native, extractions, emulated) or `no`; `first` = how the chain's first model carries it."""
    out = {}
    for need, spec in needs().items():
        kinds = list(dict.fromkeys(list(spec.get("types") or []) + list(spec.get("new_kinds") or {})))
        rows = {}
        for k in kinds:
            per = {}
            for m in chain:
                cap = capabilities(provider_of(m), m)
                per[m] = "native" if k in cap["native"] else "extractions" if k in cap["extract"] else \
                    "emulated" if k in cap["emulate"] else "no"
            rows[k] = {"asked": k in (spec.get("types") or []), "first": per[chain[0]] if chain else "no",
                       "any": next((f"{m}: {h}" for m, h in per.items() if h != "no"), "no"), "models": per}
        out[need] = rows
    return out


def policy(need: str | None) -> dict:
    out = dict(DEFAULT_POLICY)
    declared = needs().get(need or "") if need else None
    if declared:
        out.update({k: declared[k] for k in DEFAULT_POLICY if k in declared})
        out["declared"] = True
    return out


# ── reuse ───────────────────────────────────────────────────────────────────────────────────────────────────────
class Memo:
    """Bounded, time-limited reuse of whole decisions, keyed by exactly what was asked."""

    def __init__(self, size: int = MEMO_SIZE):
        self.size, self.items, self.lock = size, OrderedDict(), threading.Lock()

    @staticmethod
    def key(models: list[str], samples: int, state, schema: str) -> str:
        return _digest({"models": models, "samples": samples, "state": state, "schema": schema})

    def get(self, key: str):
        with self.lock:
            hit = self.items.get(key)
            if not hit:
                return None
            if hit[0] < time.monotonic():
                del self.items[key]
                return None
            self.items.move_to_end(key)
            return copy.deepcopy(hit[1])

    def put(self, key: str, value: dict, ttl: float) -> None:
        if not ttl or ttl <= 0:
            return
        with self.lock:
            self.items[key] = (time.monotonic() + float(ttl), copy.deepcopy(value))
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.items.clear()


MEMO = Memo()


# ── confidence and escalation ───────────────────────────────────────────────────────────────────────────────────
def confidence(answer) -> float | None:
    """How sure the model was of one answer: a choice's confidence (else its top probability), a noul's distance
    from even odds as max(p, 1 - p). None for the types that carry no probability."""
    if not isinstance(answer, dict):
        return None
    if isinstance(answer.get("noul"), (int, float)) and not isinstance(answer.get("noul"), bool):
        p = float(answer["noul"])
        return max(p, 1 - p)
    probs = answer.get("probabilities")
    if isinstance(answer.get("choices"), list) and isinstance(probs, dict) and probs:
        vals = [float(v) for v in probs.values() if _num(v)]       # several options: the least sure of them
        return min(max(v, 1 - v) for v in vals) if vals else None
    if _num(answer.get("found")) and answer.get("type") in ("text", "number", "date", "box"):
        f = float(answer["found"])                                   # a value read (or not): sure of either
        return max(f, 1 - f)
    c = answer.get("confidence")
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return float(c)
    probs = answer.get("probabilities")
    if isinstance(probs, dict) and probs:
        vals = [v for v in probs.values() if isinstance(v, (int, float))]
        return float(max(vals)) if vals else None
    return None


def confidences(answers: dict) -> dict:
    return {k: round(c, 3) for k, a in (answers or {}).items() if (c := confidence(a)) is not None}


def uncertain(answers: dict, below: float | None) -> list[str]:
    if below is None:
        return []
    return [k for k, c in confidences(answers).items() if c < float(below)]
