"""Long owner text for a decision model: a representation that never loses the end and keeps provenance.

The preflight used to send `message[:1500]`: an instruction, a negation or a constraint written after that point
was invisible to the decision (« …et surtout ne supprime rien » at the end of a 6 000-character brief). This module
replaces the cut with a deterministic, model-free representation:

    head + every sentence that carries an instruction / negation / constraint / date / amount / question + tail

Gaps are said, never silent: `[…N caractères omis, offsets a–b…]`, and the header gives the full length. Offsets are
characters of the ORIGINAL text, so the original can always be re-read (walter_logs keeps it). Detectors cover French
and English. No generalist model summary: a summary would be one more place to lose a « ne pas ».

    represent(text) -> Long        .text (what the model reads), .length, .truncated, .parts (provenance)
    long_text(text, limit=None) -> str
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import longtext_settings

# kind → (weight, regex). Negations and prohibitions weigh most: they invert the meaning of everything before them.
_NEG = (r"\b(?:ne|n['’])\s*(?:\w+['’]?\s+){0,3}?(?:pas|jamais|plus|rien|aucun\w*|nulle?ment|point)\b",
        r"\b(?:jamais|interdit\w*|surtout\s+pas|évite[rz]?|eviter|sans|hors\s+de\s+question|pas\s+question)\b",
        r"\b(?:don['’]?t|do\s+not|never|must\s+not|mustn['’]?t|shouldn['’]?t|should\s+not|cannot|can['’]?t|won['’]?t|"
        r"avoid|without|no\s+longer|stop|not\s+to|forbidden|prohibited|nothing|none)\b")
_INSTR = (r"\b(?:il\s+faut|il\s+ne\s+faut|tu\s+dois|vous\s+devez|dois|doit|doivent|assure[- ]?toi|n['’]oublie|"
          r"obligatoire|imp[ée]ratif|uniquement|seulement|exactement|au\s+plus|au\s+moins|maximum|minimum|toujours|"
          r"[àa]\s+condition|sauf|quoi\s+qu['’]il|priorit[ée]|d['’]abord|ensuite|enfin|avant\s+de|apr[èe]s\s+avoir|"
          r"pense\s+[àa]|rappelle|retiens|note\s+que|attention|important|veille\s+[àa])\b",
          r"\b(?:must|should|need\s+to|needs\s+to|make\s+sure|ensure|always|only|at\s+most|at\s+least|unless|except|"
          r"required|mandatory|before|after|first|then|finally|remember|note\s+that|important|careful|please|"
          r"has\s+to|have\s+to)\b",
          r"(?:^|[.!?\n]\s*)(?:fais|fait|envoie|supprime|ajoute|mets|utilise|cr[ée]e|change|corrige|arr[êe]te|"
          r"v[ée]rifie|pr[ée]pare|[ée]cris|lance|annule|remplace|garde|r[ée]ponds|commence|termine|finis|"
          r"do|make|send|delete|remove|add|use|create|change|fix|check|write|run|cancel|replace|keep|reply|start|"
          r"finish|update|set|put|give)\b")
_DATE = (r"\b\d{4}-\d{2}-\d{2}\b", r"\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b", r"\b\d{1,2}\s*h(?:\s*\d{2})?\b",
         r"\b\d{1,2}:\d{2}\b",
         r"\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain|ce\s+soir|ce\s+matin|aujourd['’]hui|"
         r"hier|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre|"
         r"semaine\s+prochaine|monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|today|"
         r"yesterday|january|february|march|april|june|july|august|september|october|november|december|"
         r"next\s+week|deadline|[ée]ch[ée]ance)\b")
_AMOUNT = (r"\d[\d\s.,]*\s?(?:€|eur\b|euros?\b|\$|usd\b|dollars?\b|£|k€|m€|%|pour\s*cent)", r"[€$£]\s?\d")
_FLAGS = re.I | re.M
KINDS = {"négation": (4, [re.compile(p, _FLAGS) for p in _NEG]),
         "consigne": (3, [re.compile(p, _FLAGS) for p in _INSTR]),
         "question": (2, [re.compile(r"\?")]),
         "date": (2, [re.compile(p, _FLAGS) for p in _DATE]),
         "montant": (2, [re.compile(p, _FLAGS) for p in _AMOUNT])}
_SPLIT = re.compile(r"(?<=[.!?…;:])\s+|\n+")


@dataclass
class Long:
    text: str                                   # the representation the model reads
    length: int                                 # characters of the original
    truncated: bool
    parts: list[dict] = field(default_factory=list)   # {"a", "b", "kind": head|tail|signal, "flags": [...]}
    omitted: int = 0


def flags(sentence: str) -> list[str]:
    """The kinds of signal a sentence carries (deterministic detectors, French + English)."""
    return [k for k, (_, pats) in KINDS.items() if any(p.search(sentence) for p in pats)]


def binding(sentence: str) -> bool:
    """A sentence that constrains the work (negation, prohibition, « il faut », « only », « at most »…): not a bare
    imperative, which is a task rather than a constraint."""
    return any(p.search(sentence) for p in KINDS["négation"][1]) or any(p.search(sentence) for p in KINDS["consigne"][1][:2])


def _score(fl: list[str]) -> int:
    return sum(KINDS[k][0] for k in fl)


def _sentences(text: str, a: int, b: int) -> list[tuple[int, int]]:
    """(start, end) offsets of the sentences of text[a:b] (original offsets)."""
    out, pos = [], a
    for m in _SPLIT.finditer(text, a, b):
        if m.start() > pos:
            out.append((pos, m.start()))
        pos = m.end()
    if pos < b:
        out.append((pos, b))
    return [(s, e) for s, e in out if text[s:e].strip()]


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _snap(text: str, i: int, direction: int, window: int = 40) -> int:
    """Move a cut to a whitespace nearby so words are not sliced (direction -1: backwards, +1: forwards)."""
    j, n = i, len(text)
    for _ in range(window):
        if j <= 0 or j >= n or text[j].isspace():
            return j
        j += direction
    return i


def represent(text: str | None, limit: int | None = None, *, settings: dict | None = None) -> Long:
    st = settings or longtext_settings()
    text = text or ""
    limit = st["inline_chars"] if limit is None else limit
    n = len(text)
    flat = _ws(text)
    if len(flat) <= limit:
        return Long(text=flat, length=n, truncated=False, parts=[{"a": 0, "b": n, "kind": "whole"}] if n else [])
    head_end = _snap(text, min(st["head_chars"], n), +1)
    tail_start = max(_snap(text, max(n - st["tail_chars"], head_end), -1), head_end)
    # candidate sentences of the middle, plus the sentence straddling a window edge is kept whole by the window itself
    cands = []
    for s, e in _sentences(text, head_end, tail_start):
        seg = text[s:e]
        fl = flags(seg)
        if fl:
            cands.append((_score(fl), s, e, fl))
    budget, chosen = st["signal_chars"], []
    for score, s, e, fl in sorted(cands, key=lambda c: (-c[0], -c[1])):      # best first, later first on a tie
        if e - s > st["signal_sentence_chars"]:                              # a long sentence: around its first hit
            seg = text[s:e]
            hit = min((m.start() for _, pats in (KINDS[k] for k in fl) for p in pats for m in [p.search(seg)] if m),
                      default=0)
            a = _snap(text, max(s + hit - st["signal_sentence_chars"] // 3, s), -1)
            e = _snap(text, min(a + st["signal_sentence_chars"], e), +1)
            s = max(a, s)
        cost = len(_ws(text[s:e])) + 40
        if cost > budget:
            continue
        budget -= cost
        chosen.append((s, e, fl))
    chosen.sort()
    parts = [{"a": 0, "b": head_end, "kind": "head"}]
    pieces = [_ws(text[:head_end])]
    pos, omitted = head_end, 0
    for s, e, fl in chosen:
        if s > pos:
            pieces.append(f"[…{s - pos} caractères omis, offsets {pos}–{s}…]")
            omitted += s - pos
        pieces.append(f"{_ws(text[s:e])} [{'/'.join(fl)}, offsets {s}–{e}]")
        parts.append({"a": s, "b": e, "kind": "signal", "flags": fl})
        pos = max(pos, e)
    if tail_start > pos:
        pieces.append(f"[…{tail_start - pos} caractères omis, offsets {pos}–{tail_start}…]")
        omitted += tail_start - pos
    pieces.append(_ws(text[tail_start:]))
    parts.append({"a": tail_start, "b": n, "kind": "tail"})
    kept = sum(1 for p in parts if p["kind"] == "signal")
    header = (f"[message long : {n} caractères ; début, fin et {kept} passage(s) à consigne, négation, contrainte, date, "
              f"montant ou question conservés mot pour mot ; {omitted} caractères omis]")
    return Long(text=header + " " + " ".join(pieces), length=n, truncated=True, parts=parts, omitted=omitted)


def long_text(text: str | None, limit: int | None = None) -> str:
    return represent(text, limit).text
