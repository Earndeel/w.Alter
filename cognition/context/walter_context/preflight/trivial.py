"""Answers the preflight can give without any model (lot 2, 2026-11-07, Monsieur: « les demandes triviales sont
répondues sans LLM »): a bare calculation, the time or the date. Only for messages the TRIVIAL rule already matched;
anything this module cannot settle exactly returns None and the model answers as before."""
from __future__ import annotations

import ast
import operator
import re
from datetime import datetime
from zoneinfo import ZoneInfo

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.USub: operator.neg, ast.UAdd: operator.pos}
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]
PERCENT_OF = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%\s*de\s*(\d+(?:[.,]\d+)?)\s*\??\s*$", re.I)
TIME = re.compile(r"^\s*quelle heure( est[- ]il)?\s*\??\s*$", re.I)
DATE = re.compile(r"^\s*(on est quel jour|quel jour sommes[- ]nous)\s*\??\s*$", re.I)


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = _eval(node.left), _eval(node.right)
        return OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    raise ValueError("not plain arithmetic")


def _number(value: float) -> str:
    if abs(value) >= 1e15:
        raise ValueError("too large")
    text = f"{value:,.6f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return text.replace(",", " ").replace(".", ",")


def calculation(text: str) -> str | None:
    m = PERCENT_OF.match(text)
    if m:
        a, b = (float(x.replace(",", ".")) for x in m.groups())
        return f"{m.group(1)} % de {m.group(2)} = {_number(a * b / 100)}"
    expr = re.sub(r"^\s*combien (font|fait)\s+", "", text, flags=re.I).strip().rstrip("?").strip()
    expr = re.sub(r"\s*[€$]\s*$", "", expr)
    if not re.fullmatch(r"[\d\s.,()+*/x×-]+", expr) or not re.search(r"\d\s*[-+*/x×]\s*[\d(]", expr):
        return None
    py = re.sub(r"(?<=\d),(?=\d)", ".", expr.replace("×", "*").replace("x", "*")).replace(" ", "")
    try:
        value = _eval(ast.parse(py, mode="eval"))
        return f"{expr} = {_number(value)}"
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
        return None


def answer(text: str, tz: str | None, now: datetime | None = None) -> str | None:
    """The exact answer, or None when a model should answer."""
    text = (text or "").strip()
    if TIME.match(text) or DATE.match(text):
        if not tz:
            return None
        zone = ZoneInfo(tz)
        at = (now or datetime.now(zone)).astimezone(zone)
        place = tz.split("/")[-1].replace("_", " ")
        if TIME.match(text):
            return f"Il est {at:%H} h {at:%M} (heure de {place})."
        return f"Nous sommes le {DAYS[at.weekday()]} {at.day} {MONTHS[at.month - 1]} {at.year} (heure de {place})."
    return calculation(text)


def owner_tz() -> str | None:
    """The owner's time zone as Walter Memory knows it (its periods setting); None if unreadable."""
    try:
        from walter_memory import organic
        return (organic.settings().get("periods") or {}).get("tz")
    except Exception:  # noqa: BLE001 — no zone known: the model answers the time
        return None
