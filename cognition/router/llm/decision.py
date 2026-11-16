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
    return questions, _digest(questions)


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
