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
DEFAULT_POLICY = {"memo_ttl_s": 0, "escalate_below": None, "max_timeout_s": None, "sampling": None}   # undeclared: no reuse
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
        if "resolve" in q and (q["resolve"] not in RESOLVE or kind not in ("spans", "date")):
            raise Invalid(f"question {name}: resolve is 'date', on spans or a date")
        if kind in ("spans", "boxes") and "max" in q:
            if isinstance(q["max"], bool) or not isinstance(q["max"], int) or not 1 <= q["max"] <= 64:
                raise Invalid(f"question {name}: max is an integer 1..64")
    return questions, _digest(questions)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


DATE_ORDERS = ("dmy", "mdy", "ymd")
WALTER_ONLY = ("order", "resolve")      # read by Walter, never sent to a provider
RESOLVE = ("date",)          # `resolve: "date"` on spans: each passage read as a calendar date by Walter (resolve_date)


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
# Images beside the state on OpenRouter Decisions (top-level state array with image_url parts): measured right on
# these two on 17/11 (count of squares, 0.5-0.7 s); OpenRouter's Extractions route takes images for estimates only,
# so an extraction part is always read from the text state.
OPENROUTER_IMAGES = frozenset({"liquid/d1.2", "liquid/d1.2-ultra"})
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
                "emulate": frozenset({"multiple"}),
                "media": frozenset({"image"}) if model in OPENROUTER_IMAGES else frozenset(), "verified": True}
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
        if q.get("resolve") == "date":
            for it in items:
                sp = it["span"]
                if isinstance(sp, list) and len(sp) == 2 and all(isinstance(x, int) for x in sp):
                    it["span"], it["text"] = _with_lead(text, sp, it["text"])
        items = items[:q["max"]] if q.get("max") else items
        return {"type": "spans", "spans": items, "count": len(items), "at_least": None}
    pn = a.get("p_null")
    found = round(1 - float(pn), 6) if _num(pn) else None
    span = a.get("span")
    ok = isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span)
    written = text[span[0]:span[1]] if ok else None
    if ok and k == "date":
        span, written = _with_lead(text, span, written)
    value = a.get("value")
    if k == "text":
        return {"type": "text", "text": value, "span": span if ok else None, "found": found}
    out = {"type": k, k: value, "text": written, "span": span if ok else None, "found": found}
    if k == "number":
        out["unit"] = q.get("unit")
        if not _num(value):         # the passage is found but its value is not given (« 300 euros », 17/11): read it
            n = parse_number(value if isinstance(value, str) else written)
            if n is not None:
                out.update(number=n, read_by="walter")
            elif value is not None:
                out["number"] = None
    return out


_NUM_IN_TEXT = re.compile(r"\d[\d\s\u00a0\u202f'.,]*")


def parse_number(text) -> float | int | None:
    """The first number written in a passage: « 1 200 € », « 89,90 € », « 1,200.50 $ », « 2k€ ». One separator
    followed by exactly three digits groups thousands; otherwise it is the decimal mark."""
    if not isinstance(text, str):
        return None
    m = _NUM_IN_TEXT.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s\u00a0\u202f']", "", m.group(0)).rstrip(".,")
    if "." in raw and "," in raw:
        dec = "." if raw.rfind(".") > raw.rfind(",") else ","
        raw = raw.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif raw.count(",") + raw.count(".") >= 1:
        sep = "," if "," in raw else "."
        groups = raw.split(sep)
        raw = "".join(groups) if (len(groups) > 2 or len(groups[-1]) == 3) else raw.replace(sep, ".")
    try:
        n = float(raw)
    except ValueError:
        return None
    if re.match(r"\s*[kK](?![a-zA-Z])|\s*[kK]€", text[m.end():]):
        n *= 1000
    return int(n) if n == int(n) else round(n, 6)


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


# ── dates written in words (2.0, 17/11) ─────────────────────────────────────────────────────────────────────────
# d1.2 finds « jeudi », « vendredi prochain », « lundi 30 » (span and found) but leaves the date null: there is no
# reference date on its routes. Walter reads them itself, against the caller's `now` (the owner's local date), and
# says when the words leave a choice (`past` = the same words read as already gone; `ambiguous`).
_WEEKDAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_MONTHS = {"janvier": 1, "janv": 1, "jan": 1, "january": 1, "février": 2, "fevrier": 2, "févr": 2, "fev": 2, "fév": 2,
           "feb": 2, "february": 2, "mars": 3, "mar": 3, "march": 3, "avril": 4, "avr": 4, "apr": 4, "april": 4,
           "mai": 5, "may": 5, "juin": 6, "june": 6, "jun": 6, "juillet": 7, "juil": 7, "july": 7, "jul": 7,
           "août": 8, "aout": 8, "aug": 8, "august": 8, "septembre": 9, "sept": 9, "sep": 9, "september": 9,
           "octobre": 10, "oct": 10, "october": 10, "novembre": 11, "nov": 11, "november": 11, "décembre": 12,
           "decembre": 12, "déc": 12, "dec": 12, "december": 12}
_OFFSETS = (("après-demain", 2), ("apres-demain", 2), ("après demain", 2), ("day after tomorrow", 2),
            ("avant-hier", -2), ("avant hier", -2), ("demain", 1), ("tomorrow", 1), ("hier", -1), ("yesterday", -1),
            ("aujourd'hui", 0), ("aujourd’hui", 0), ("today", 0), ("ce soir", 0), ("ce matin", 0), ("tonight", 0),
            ("cet après-midi", 0), ("this afternoon", 0), ("this evening", 0))
_NUMBERS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
            "neuf": 9, "dix": 10, "quinze": 15, "one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15}
_N = r"(\d{1,3}|" + "|".join(sorted(_NUMBERS, key=len, reverse=True)) + r")"
_IN = re.compile(r"(?<![\w])(?:dans|d'ici|sous|in|within)\s+" + _N + r"\s+(jours?|days?|semaines?|weeks?)\b")
# a duration the model read without its preposition (« 10 jours » of « dans 10 jours », 17/11 bench): the day it names
# depends on it, so it is taken back from the passage
_DURATION = re.compile(r"^\s*(?:\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|quinze)\s+"
                       r"(?:jours?|days?|semaines?|weeks?)\s*$", re.I)
_LEAD = re.compile(r"(?:dans|d'ici|sous|in|within)\s+$", re.I)


def _with_lead(text: str, span: list, written: str | None) -> tuple[list, str | None]:
    if not written or not _DURATION.match(written):
        return span, written
    before = text[max(0, span[0] - 10):span[0]]
    m = _LEAD.search(before.replace("’", "'"))
    if not m:
        return span, written
    start = span[0] - (len(before) - m.start())
    return [start, span[1]], text[start:span[1]]
_AGO = re.compile(r"\b(?:il y a\s+" + _N + r"\s+(jours?|semaines?)|" + _N + r"\s+(days?|weeks?)\s+ago)\b")
_TIME = re.compile(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b|\b(\d{1,2})\s*(am|pm)\b")
_DAYNUM = re.compile(r"\b(\d{1,2})(?:er|st|nd|rd|th)?\b")
_YEAR = re.compile(r"\b(20\d{2})\b")


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBERS[word]


def _today(now) -> "datetime.date":
    import datetime
    if isinstance(now, str) and now:
        try:
            return datetime.date.fromisoformat(now[:10])
        except ValueError:
            pass
    return datetime.datetime.now(datetime.timezone.utc).date()


def resolve_date(text: str, now=None, order: str = "dmy") -> dict | None:
    """Words of a date → {date, past?, time?, ambiguous?} against `now` (ISO date); None when they name no day."""
    import datetime
    if not isinstance(text, str) or not text.strip():
        return None
    t = " ".join(text.lower().replace("’", "'").split())
    today = _today(now)
    out: dict = {}
    m = _TIME.search(t)
    if m:
        h, mi = (int(m.group(1)), int(m.group(2) or 0)) if m.group(1) else \
            ((int(m.group(3)) % 12) + (12 if m.group(4) == "pm" else 0), 0)
        if 0 <= h < 24 and 0 <= mi < 60:
            out["time"] = f"{h:02d}:{mi:02d}"
    named = [v for k, v in _WEEKDAYS.items() if re.search(r"(?<![\w])" + k + r"(?![\w])", t)]
    bare = _TIME.sub(" ", t)                               # « mardi 25/11 à 14h » reads as « 25/11 »
    for k in _WEEKDAYS:
        bare = re.sub(r"(?<![\w])" + k + r"(?![\w])", " ", bare)
    bare = re.sub(r"(?<![\w])(?:à|a|at|vers|around)(?![\w])", " ", bare)
    bare = re.sub(r"^\s*(?:le|the|on)\s+", "", " ".join(bare.replace(",", " ").split()))

    def _said(day):                                        # a weekday that is not that date's: say it, keep the date
        return {**out, "date": day.isoformat(), **({"ambiguous": True} if named and day.weekday() != named[0] else {})}
    num = _NUMERIC_DATE.match(bare)
    if num:
        parts = dict(zip(order, (int(x) for x in num.groups())))
        y = parts["y"] + 2000 if parts["y"] < 100 else parts["y"]
        try:
            return _said(datetime.date(y, parts["m"], parts["d"]))
        except ValueError:
            return None
    short = re.match(r"^\s*(\d{1,2})\s*[/.]\s*(\d{1,2})\s*$", bare)   # « 05/12 »: the next such day
    if short:
        a, b = int(short.group(1)), int(short.group(2))
        d, mo = (a, b) if order != "mdy" else (b, a)
        for y in (today.year, today.year + 1):
            try:
                day = datetime.date(y, mo, d)
            except ValueError:
                return None
            if day >= today:
                return _said(day)
    for words, delta in _OFFSETS:
        if re.search(r"(?<![\w-])" + re.escape(words) + r"(?![\w-])", t):
            return {**out, "date": (today + datetime.timedelta(days=delta)).isoformat()}
    m = _IN.search(t)
    if m:
        n = _count(m.group(1)) * (7 if m.group(2).startswith(("sem", "week")) else 1)
        return {**out, "date": (today + datetime.timedelta(days=n)).isoformat()}
    m = _AGO.search(t)
    if m:
        n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        n = _count(n) * (7 if unit.startswith(("sem", "week")) else 1)
        return {**out, "date": (today - datetime.timedelta(days=n)).isoformat()}
    month = next((v for k, v in _MONTHS.items() if re.search(r"(?<![\w])" + re.escape(k) + r"\.?(?![\w])", t)), None)
    weekday = next((v for k, v in _WEEKDAYS.items() if re.search(r"(?<![\w])" + k + r"(?![\w])", t)), None)
    words_only = _TIME.sub(" ", t)
    dn = _DAYNUM.search(_YEAR.sub(" ", words_only))
    daynum = int(dn.group(1)) if dn and 1 <= int(dn.group(1)) <= 31 else None
    ym = _YEAR.search(t)
    if month and daynum:                                   # « 3 décembre », « le 30 nov. 2026 »
        years = [int(ym.group(1))] if ym else [today.year, today.year + 1]
        for y in years:
            try:
                day = datetime.date(y, month, daynum)
            except ValueError:
                return None
            if ym or day >= today - datetime.timedelta(days=1):
                res = {**out, "date": day.isoformat()}
                if weekday is not None and day.weekday() != weekday:
                    res["ambiguous"] = True               # « lundi 3 décembre » when the 3rd is not a Monday
                return res
        return None
    if weekday is not None and daynum:                     # « lundi 30 »: the nearest month where the 30th is a Monday
        y, mo = today.year, today.month
        for _ in range(13):
            try:
                day = datetime.date(y, mo, daynum)
                if day.weekday() == weekday and day >= today - datetime.timedelta(days=7):
                    return {**out, "date": day.isoformat()}
            except ValueError:
                pass
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        return None
    if weekday is not None:
        ahead = (weekday - today.weekday()) % 7 or 7
        back = (today.weekday() - weekday) % 7 or 7
        nxt = today + datetime.timedelta(days=ahead)
        prev = today - datetime.timedelta(days=back)
        if re.search(r"\b(dernier|passé|passe|last)\b", t):
            return {**out, "date": prev.isoformat()}
        if re.search(r"\b(prochain|next)\b", t):
            return {**out, "date": nxt.isoformat(), **({"ambiguous": True} if ahead <= 6 else {})}
        if re.search(r"\b(ce|this|cette)\b", t):
            return {**out, "date": nxt.isoformat()}
        return {**out, "date": nxt.isoformat(), "past": prev.isoformat(), "ambiguous": True}
    if daynum and re.match(r"^\s*(le\s+|the\s+)?\d{1,2}(er|st|nd|rd|th)?\s*$", words_only):   # « le 3 »
        y, mo = today.year, today.month
        for _ in range(2):
            try:
                day = datetime.date(y, mo, daynum)
                if day >= today:
                    return {**out, "date": day.isoformat()}
            except ValueError:
                pass
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return None


def resolve(questions: dict, answers: dict, now=None) -> dict:
    """`resolve: "date"`: every passage of a spans answer, and a date the model found but could not read, read by
    Walter as a calendar date (`read_by: walter`). Deterministic; the passage itself is kept as written."""
    out = None
    for name, q in questions.items():
        if q.get("resolve") != "date" or not isinstance(answers.get(name), dict):
            continue
        a, order = answers[name], q.get("order") or "dmy"
        if q.get("type") == "spans" and isinstance(a.get("spans"), list):
            items = []
            for it in a["spans"]:
                got = resolve_date((it or {}).get("text"), now, order) if isinstance(it, dict) else None
                items.append({**it, **got, "read_by": "walter"} if got else it)
            out = out if out is not None else dict(answers)
            out[name] = {**a, "spans": items}
        elif q.get("type") == "date" and a.get("date") is None and _num(a.get("found")) and a["found"] >= NOT_FOUND:
            got = resolve_date(a.get("text"), now, order)
            if got:
                out = out if out is not None else dict(answers)
                out[name] = {**a, **got, "read_by": "walter"}
    return answers if out is None else out


# ── signals: what the modules declare, composed per event (2.0, 17/11) ──────────────────────────────────────────
# Modules declare their questions as signals (Core: `walter decisions`, walter_platform/decisions.py). For one event
# Walter Decision keeps the signals of its occasion whose facts hold (the caller's facts + the cues it reads itself
# in the state, without a model), fills the criteria the caller provides (`options_from`), asks a question two modules
# declared identically once, and says what it left out and why. No model call; the result is cached by its inputs.
_CUES = (("cue.date", re.compile(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|monday|tuesday|wednesday|"
                                 r"thursday|friday|saturday|sunday|demain|tomorrow|hier|yesterday|aujourd|today|"
                                 r"semaines?|weeks?|janv|févr|fevr|mars|avril|mai|juin|juil|août|aout|sept|oct|nov|déc|dec|"
                                 r"janvier|février|fevrier|juillet|septembre|octobre|novembre|décembre|decembre|"
                                 r"january|february|march|april|june|july|august|october|november|december|"
                                 r"ce soir|tonight|dans \d+ (jours?|semaines?)|in \d+ (days?|weeks?)|"
                                 r"\d{1,2}\s*h\s*\d{0,2}|\d{1,2}[/.]\d{1,2}([/.]\d{2,4})?|\d{4}-\d{2}-\d{2}|"
                                 r"(avant|après|d'ici|jusqu'au|before|until|by) (le |the )?\d)\b", re.I)),
         ("cue.amount", re.compile(r"(\d[\d\s.,]*\s?(€|eur|euros?|\$|usd|dollars?|£|chf|k€|m€)(?!\w)|[€$£]\s?\d)", re.I)),
         ("cue.contact", re.compile(r"([\w.+-]+@[\w-]+\.[\w.]+|(\+|00)\d[\d\s.]{7,}|\b0[1-9](\s?\d{2}){4}\b)")),
         ("cue.person", re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b|@\w{3,}|\b(avec|with|à|to|de|from|"
                                   r"chez|pour|for)\s+[A-ZÀ-Ý][a-zà-ÿ]+", re.M)),
         ("cue.number", re.compile(r"\b\d+([.,]\d+)?\b")))


def cues(text: str) -> set:
    """Facts read in the text without a model: is there something that looks like a date, an amount, a contact, a
    name, a number. They only open a question; the model still reads the value."""
    t = text or ""
    return {name for name, rx in _CUES if rx.search(t)}


def state_text(state) -> str:
    """The text of a state (a JSON state's string values), for the cues."""
    if isinstance(state, str):
        return state
    if isinstance(state, list):
        return " ".join(state_text(x) for x in state if not (isinstance(x, dict) and x.get("type") == "image_url"))
    if isinstance(state, dict):
        return " ".join(state_text(v) for v in state.values())
    return str(state) if isinstance(state, (int, float)) else ""


def holds(when, facts) -> bool:
    """Every term of `when` holds: a fact, `!fact` (absent), or `a|b|!c` (any of them)."""
    def one(term):
        return term[1:] not in facts if term.startswith("!") else term in facts
    return all(any(one(p) for p in term.split("|")) for term in when or ())


_COMPOSED: "OrderedDict[str, dict]" = OrderedDict()
_COMPOSED_LOCK = threading.Lock()


def compose(signals: list, occasion: str, facts=(), options: dict | None = None, *, registry: str = "",
            only=None, layers=None) -> dict:
    """The decision of one event from the declared signals → {questions, ids: {signal id: question key}, asked,
    skipped: {id: reason}, required, schema, registry}. Raises Invalid when a selected signal is not in the language
    (an owner's mistake is named, never asked). `only`: the signal ids a complementary decision asks (the rest of the
    occasion is not asked again; their `when` still holds or they are skipped). `layers`: observation and/or
    inference — a caller that does not wait for the readings to act asks them apart, in parallel."""
    facts = set(facts or ())
    options = options or {}
    only = None if only is None else set(only)
    key = _digest({"r": registry or _digest(signals), "o": occasion, "f": sorted(facts), "x": options,
                   "a": sorted(only) if only is not None else None, "l": sorted(layers) if layers else None})
    with _COMPOSED_LOCK:
        if key in _COMPOSED:
            _COMPOSED.move_to_end(key)
            return copy.deepcopy(_COMPOSED[key])
    questions, ids, skipped, required, seen, asked = {}, {}, {}, [], {}, []
    names = [s.get("name") for s in signals if occasion in (s.get("occasions") or ())]
    for s in signals:
        sid = s.get("id")
        if occasion not in (s.get("occasions") or ()):
            continue
        if only is not None and sid not in only:
            continue
        if layers and s.get("layer") not in layers:
            continue
        if not holds(s.get("when"), facts):
            skipped[sid] = "when: " + " ".join(s.get("when") or ())
            continue
        q = copy.deepcopy(s.get("question") or {})
        src = s.get("options_from")
        if src:
            given = options.get(src)
            if not isinstance(given, dict) or not given:
                skipped[sid] = f"options_from: no {src}"
                continue
            q["criteria"] = {**{str(k): str(v) for k, v in given.items()}, **(q.get("criteria") or {})}
        digest = _digest(q)
        if digest in seen:                                  # the same question twice: asked once, answered to both
            ids[sid] = seen[digest]
            asked.append(sid)
            if s.get("required"):
                required.append(sid)
            continue
        name = s.get("name") or sid
        qkey = name if names.count(name) == 1 else sid      # a name two modules use: their ids tell them apart
        questions[qkey] = q
        seen[digest] = qkey
        ids[sid] = qkey
        asked.append(sid)
        if s.get("required"):
            required.append(sid)
    if questions:
        try:
            questions, schema = compile_questions(questions)
        except Invalid as exc:
            bad = str(exc).split(":")[0].replace("question ", "")
            owner = next((sid for sid, k in ids.items() if k == bad), bad)
            raise Invalid(f"signal {owner}: {exc}") from None
    else:
        schema = None
    out = {"questions": questions, "ids": ids, "asked": asked, "skipped": skipped, "required": required,
           "schema": schema, "registry": registry, "facts": sorted(facts)}
    with _COMPOSED_LOCK:
        _COMPOSED[key] = copy.deepcopy(out)
        while len(_COMPOSED) > 256:
            _COMPOSED.popitem(last=False)
    return out


def by_signal(composed: dict, answers: dict) -> dict:
    """Answers keyed by signal id (None = asked, not answered)."""
    return {sid: answers.get(k) for sid, k in composed["ids"].items()}
