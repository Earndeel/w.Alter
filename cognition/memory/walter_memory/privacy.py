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


def tighten_derived_sources(processor='l3.conversation_summary', *, dry_run=True, backup_dir=None):
    """Tighten the class of derived items (and their search chunks) to the strictest class of their sources.

    No source content is modified or printed. (Until 2026-11-09 it also tagged the Hindsight copies; the Hindsight
    tables were dropped in cleanup phase 1.)
    """
    from .db import connection
    from datetime import datetime, timezone
    from pathlib import Path
    import os
    with connection() as conn:
        rows=conn.execute("""select d.item_id,d.privacy_class,d.source_refs,
                    max(case e.privacy_class when 'local_only' then 2 when 'redacted_cloud' then 1 else 0 end) source_rank
                from core.derived_items d join lateral unnest(d.source_event_ids) r(eid) on true
                join core.events e on e.event_id=r.eid where d.derived_by=%s
                group by d.item_id having max(case e.privacy_class when 'local_only' then 2 when 'redacted_cloud' then 1 else 0 end)
                  > case d.privacy_class when 'local_only' then 2 when 'redacted_cloud' then 1 else 0 end""",(processor,)).fetchall()
        ids=[r['item_id'] for r in rows]
        chunks=conn.execute("select chunk_id,privacy_class from search.chunks where kind='derived' and ref_id=any(%s)",(ids,)).fetchall() if ids else []
        out={'dry_run':dry_run,'items':len(ids),'search_chunks':len(chunks)}
        if dry_run or not ids:return out
        if backup_dir is None:raise ValueError('backup_dir required before privacy changes')
        folder=Path(backup_dir);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=folder/('privacy-before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'derived':rows,'chunks':chunks},f,default=str)
        for r in rows:
            cls=ORDER[r['source_rank']];looser=ORDER[:r['source_rank']]
            conn.execute('update core.derived_items set privacy_class=%s where item_id=%s and privacy_class=any(%s)',(cls,r['item_id'],looser))
            conn.execute("update search.chunks set privacy_class=%s where kind='derived' and ref_id=%s and privacy_class=any(%s)",(cls,r['item_id'],looser))
        conn.execute("""insert into system.audit_log(actor,action,target,details)
                        values ('walter-memory','privacy.tighten_derived_sources',%s,%s::jsonb)""",
                     (processor,json.dumps({**out,'items_changed':[str(i) for i in ids],'backup':str(path)})))
        out['backup']=str(path)
        return out


def cloud_ceiling() -> str:
    """The strictest class a cloud reader (a cloud model's context or call, MCP tools of cloud agents) may read.
    organic.toml [privacy] cloud_context: "cloud_allowed" (the strict rule before 2026-11-03), "redacted_cloud", or
    "local_only" (Monsieur, 2026-11-03: Walter has no local model, all its reasoning is cloud — « oui tout »).
    Classes stay on every row (audit, a future local model, a stricter setting); only who may read them changes.
    What leaves towards a PERSON is decided apart (disclosure.py)."""
    try:
        from . import organic
        c = (organic.settings().get("privacy") or {}).get("cloud_context", "cloud_allowed")
    except Exception:
        c = "cloud_allowed"
    return c if c in ORDER else "cloud_allowed"


def pseudonymise() -> bool:
    """organic.toml [privacy] pseudonymise: redacted_cloud content is pseudonymised before a cloud model sees it
    (default true; Monsieur, 2026-11-03: not needed for now)."""
    try:
        from . import organic
        return bool((organic.settings().get("privacy") or {}).get("pseudonymise", True))
    except Exception:
        return True


def allowed_classes(max_privacy: str) -> list[str]:
    """Classes a caller may read. 'cloud_allowed' = a cloud reader → up to cloud_ceiling(); 'local_only' →
    everything; 'redacted_cloud' → cloud_allowed and redacted_cloud."""
    if max_privacy == "cloud_allowed":
        max_privacy = cloud_ceiling()
    return ORDER[: ORDER.index(max_privacy) + 1]


def mask_secrets(text: str | None) -> str | None:
    """Credentials (passwords, codes, keys, IBAN, cards) are masked in place — the message stays readable, the value
    never reaches a model (Monsieur's rule: credentials live in Bitwarden only)."""
    if not text:
        return text
    from .logs import mask
    return mask(text)


def model_may_receive(cls: str | None) -> bool:
    """May a cloud model CALL receive data of this class? redacted_cloud always could (pseudonymised when
    pseudonymise() is on); local_only only when the cloud ceiling allows it (no local model: « oui tout »)."""
    return (cls or "local_only") != "local_only" or cloud_ceiling() == "local_only"


def model_classes() -> list[str]:
    return [c for c in ORDER if model_may_receive(c)]


def cloud_readable(cls: str | None) -> bool:
    return (cls or "local_only") in allowed_classes("cloud_allowed")


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
CARD = re.compile(r"(?<![\d][ -])(?<!\d)\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,4}(?![ -]?\d)")   # printed card, not a list
CARD_CONTEXT = re.compile(r"(?i)\b(carte|card|visa|mastercard|amex|\bcb\b|cvv|expir)")
CARD_BARE = re.compile(r"\b\d{13,19}\b")

CATEGORY_PATTERNS = {
    "identity_doc": re.compile(r"(?i)\b(num[ée]ro de passeport|passport (?:number|no)|n[°o] de s[ée]curit[ée] sociale|"
                               r"social security number|carte d'identit[ée] n|permis de conduire n)\b"),
    "health": re.compile(r"(?i)\b(m[ée]decin traitant|mon m[ée]decin|ordonnance m[ée]dicale|ordonnance|prescription m[ée]dicale|"
                         r"h[ôo]pital|hospitali[sz]\w*|urgences m[ée]dicales|maladie|sympt[ôo]mes?|traitement m[ée]dical|"
                         r"psychiatr\w*|psychologue|antid[ée]presseurs?|antidepressants?|th[ée]rapeute|kin[ée]sith[ée]rapeute|"
                         r"s[ée]ropositi\w*|\bVIH\b|\bHIV\b|cancer|chimioth[ée]rapie|prise de sang|blood test|"
                         r"rendez-vous m[ée]dical|my doctor|mon dentiste|bless[ée] au|douleur (?:au|à la|aux) )"),
    "intimate": re.compile(r"(?i)\b(nudes?|nue?s?\b(?: photo)?|photos? (?:sexy|coquines?|hot)|sexting|sex ?tape|porn\w*|"
                           r"orgasm\w*|blowjob|sexe|sexuel\w*|sexy|baiser|baise[rz]?\b|coucher avec|plan cul|"
                           r"fesses|seins|cul\b|bite\b|chatte\b|nichons|lingerie|horny|fuck(?:ing)? (?:me|her|you)|"
                           r"dick\b|pussy|boobs|tits\b|ass\b|cum\b|threesome|plan à trois|escort\w*|onlyfans|"
                           r"\d(?:[.,]5)?/5 (?:seins|cul|fesses|visage|body|corps))"),
    "finance": re.compile(r"(?i)\b(relev[ée] bancaire|bank statement|virement de \d|wire transfer|solde (?:du compte|bancaire)|"
                          r"account balance|d[ée]claration d'imp[ôo]ts|tax return|salaire de \d|salary of \d)\b"),
}


def detect(text: str | None) -> list[tuple[str, str]]:
    """Return [(category, rule)] for the content. Never returns the matched text."""
    if not text:
        return []
    found = [("secret", name) for name, rx in SECRET_PATTERNS if rx.search(text)]
    candidates = list(CARD.finditer(text))
    # bare digit runs only count right after a card word (e.g. "carte: 4111…", "card_number 4111…")
    candidates += [m for m in CARD_BARE.finditer(text) if CARD_CONTEXT.search(text[max(0, m.start() - 40):m.start()])]
    for m in candidates:
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


def rescan(batch: int = 5000) -> dict:
    """Re-run detectors over stored rows and TIGHTEN privacy classes where needed (never loosen).
    Events: allowed by the append-only trigger (privacy_class tightening only). Derived items and search chunks too."""
    from .db import connection
    out = {"events": 0, "derived": 0, "chunks": 0}
    for table, key, text_sql, ref_sql, target in (
            ("core.events", "event_id", "coalesce(content,'') || ' ' || payload::text", "source || ':' || source_id", "event"),
            ("core.derived_items", "item_id", "content", "item_id::text", "derived"),
            ("search.chunks", "chunk_id", "text", "chunk_id::text", None)):
        last = None
        while True:
            with connection() as conn:
                rows = conn.execute(f"""select {key} as k, {text_sql} as t, privacy_class as cls, source_x as src, {ref_sql} as ref
                                        from (select *, {'source' if table != 'core.derived_items' else 'derived_by'} as source_x
                                              from {table}) x
                                        where privacy_class <> 'local_only' {'and ' + key + ' > %s' if last is not None else ''}
                                        order by {key} limit %s""",
                                    ((last, batch) if last is not None else (batch,))).fetchall()
                if not rows:
                    break
                last = rows[-1]["k"]
                for r in rows:
                    det = detect(r["t"])
                    if not det:
                        continue
                    cls, _ = classify(conn, {"source": r["src"], "categories": {c for c, _ in det}})
                    cls = strictest(cls, r["cls"])
                    if cls != r["cls"]:
                        conn.execute(f"update {table} set privacy_class = %s where {key} = %s", (cls, r["k"]))
                        out[{"core.events": "events", "core.derived_items": "derived", "search.chunks": "chunks"}[table]] += 1
                        if target:
                            for cat, rule in dict.fromkeys(det):
                                conn.execute("""insert into privacy.detections (target_type, target_ref, category, rule, action)
                                                values (%s, %s, %s, %s, %s)""",
                                             (target, r["ref"], cat, rule, "flagged_for_purge" if cat == "secret" else "classified_" + cls))
    return out
