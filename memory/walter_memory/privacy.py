"""Privacy classes (A6/D5): local_only > redacted_cloud > cloud_allowed. Most restrictive wins.

classify_event()  — at ingestion: source default + matching policies + content detectors.
redact()/restore() — reversible pseudonymisation for redacted_cloud before any cloud call (mapping stays local).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

ORDER = ["cloud_allowed", "redacted_cloud", "local_only"]          # increasing restriction
_policies: list[dict] = []
_policies_at = 0.0
_source_defaults: dict[str, str] = {}


def strictest(*classes: str | None) -> str:
    return max((c for c in classes if c), key=ORDER.index, default="cloud_allowed")


def allowed_classes(max_privacy: str) -> list[str]:
    """Classes a caller may read. 'cloud_allowed' → only cloud_allowed rows; 'local_only' → everything."""
    return ORDER[: ORDER.index(max_privacy) + 1]


# ───────────────────────── detectors (deterministic, L0) ─────────────────────────
def _luhn(digits: str) -> bool:
    d = [int(x) for x in digits][::-1]
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0


SECRET_PATTERNS = [
    ("api_key", re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|sk-or-v1-[a-f0-9]{32,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}"
                           r"|github_pat_[A-Za-z0-9_]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|glpat-[A-Za-z0-9_-]{20,})\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AGE-SECRET-KEY-1[0-9A-Z]{20,}")),
    ("password_stmt", re.compile(r"(?i)\b(mot de passe|password|passwd|mdp|pwd|passcode|code pin|pin code|code secret)\b\s*"
                                 r"(?:est|is|=|:|:=)\s*\S{4,}")),
    ("otp", re.compile(r"(?i)\b(code de (?:vérification|verification|confirmation)|verification code|OTP|2FA)\b\D{0,20}\b\d{4,8}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b")),
    ("cvv", re.compile(r"(?i)\b(cvv|cvc|cryptogramme)\b\D{0,10}\b\d{3,4}\b")),
]
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

CATEGORY_PATTERNS = {
    "identity_doc": re.compile(r"(?i)\b(num[ée]ro de passeport|passport (?:number|no)|n[°o] de s[ée]curit[ée] sociale|"
                               r"social security number|carte d'identit[ée] n|permis de conduire n)\b"),
    "health": re.compile(r"(?i)\b(diagnostic|diagnosis|ordonnance|prescription|m[ée]decin|doctor|h[ôo]pital|hospital|"
                         r"maladie|disease|th[ée]rapie|therapy|psychiatr\w*|antid[ée]presseur|antidepressant|"
                         r"s[ée]ropositi\w*|\bVIH\b|\bHIV\b|IST\b|STD\b|cancer|chimioth[ée]rapie|blood test|prise de sang)\b"),
    "intimate": re.compile(r"(?i)\b(nude|nudes|nu[e]?s? photo|sexting|sex tape|porn\w*|orgasm\w*|blowjob|"
                           r"sexe oral|baiser ce soir|fuck me|horny)\b"),
    "finance": re.compile(r"(?i)\b(relev[ée] bancaire|bank statement|virement de \d|wire transfer|solde (?:du compte|bancaire)|"
                          r"account balance|d[ée]claration d'imp[ôo]ts|tax return|salaire de \d|salary of \d)\b"),
}


def detect(text: str | None) -> list[tuple[str, str]]:
    """Return [(category, rule)] for the content. Never returns the matched text."""
    if not text:
        return []
    found = [("secret", name) for name, rx in SECRET_PATTERNS if rx.search(text)]
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            found.append(("secret", "card_number")); break
    found += [(cat, cat) for cat, rx in CATEGORY_PATTERNS.items() if rx.search(text)]
    return found


# ───────────────────────── policies ─────────────────────────
def _load(conn) -> None:
    global _policies, _policies_at, _source_defaults
    if _policies and time.time() - _policies_at < 60:
        return
    _policies = conn.execute("select name, match, class from privacy.policies where enabled").fetchall()
    _source_defaults = {r["source"]: r["privacy_default"] for r in
                        conn.execute("select source, privacy_default from core.sources").fetchall()}
    _policies_at = time.time()


def _matches(match: dict, facts: dict) -> bool:
    for k, v in match.items():
        fv = facts.get(k)
        if k == "mime_prefix":
            if not (facts.get("mime") or "").startswith(v):
                return False
        elif k == "category":
            if v not in facts.get("categories", ()):
                return False
        elif isinstance(v, list):
            if fv not in v:
                return False
        elif str(fv) != str(v):
            return False
    return True


def classify(conn, facts: dict) -> tuple[str, list[dict]]:
    """facts: source, source_account, event_type, thread_id, identity_id, kardex_contact_id, mime, object_kind,
    categories (detected). Returns (class, matched policies)."""
    _load(conn)
    hits = [p for p in _policies if _matches(p["match"], facts)]
    cls = strictest(_source_defaults.get(facts.get("source"), "cloud_allowed"), *(p["class"] for p in hits))
    return cls, hits


def classify_event(conn, event: dict) -> str:
    detections = detect(event.get("content")) + detect(json.dumps(event.get("payload") or {}, ensure_ascii=False)
                                                        if event.get("payload") else None)
    facts = {"source": event.get("source"), "source_account": event.get("source_account") or "",
             "event_type": event.get("event_type"), "thread_id": event.get("thread_id"),
             "categories": {c for c, _ in detections}}
    cls, _ = classify(conn, facts)
    ref = f"{event.get('source')}:{event.get('source_id')}"
    for cat, rule in dict.fromkeys(detections):
        conn.execute("""insert into privacy.detections (target_type, target_ref, category, rule, action)
                        values ('event', %s, %s, %s, %s)""",
                     (ref, cat, rule, "flagged_for_purge" if cat == "secret" else "classified_" + cls))
    return cls


# ───────────────────────── reversible pseudonymisation ─────────────────────────
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d .-]{7,}\d(?!\w)")
URL_TOKEN = re.compile(r"([?&](?:token|key|sig|code|session)=)[^&\s]+", re.I)


def redact(text: str, names: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Replace e-mails, phone numbers, URL tokens and the given person names by placeholders.
    Returns (redacted_text, mapping placeholder → original); the mapping must never leave the VM."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def sub(kind: str, original: str) -> str:
        for k, v in mapping.items():
            if v == original:
                return k
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"[{kind}_{counters[kind]}]"
        mapping[ph] = original
        return ph

    text = URL_TOKEN.sub(lambda m: m.group(1) + sub("TOKEN", m.group(0)[len(m.group(1)):]), text)
    text = EMAIL.sub(lambda m: sub("EMAIL", m.group()), text)
    text = PHONE.sub(lambda m: sub("PHONE", m.group()), text)
    for name in sorted({n for n in names or [] if n and len(n) >= 2}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", lambda m: sub("PERSON", m.group()), text)
    return text, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    for ph, original in mapping.items():
        text = text.replace(ph, original)
    return text
