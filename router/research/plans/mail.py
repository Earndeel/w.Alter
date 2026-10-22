"""Plan changes read from billing e-mails (owner, 2026-10-22: « par events en analysant les mails »). Walter Memory
keeps only human exchanges, so receipts are not in core.events: this reads the owner's Gmail directly (read-only
grant `google-memory`, through the walter-secret command), only subscription mails from AI vendors (and Google Play / Payments for Google AI plans).
Extraction is deterministic (sender domain, plan name, amount, cancel / upgrade words) — no e-mail content leaves the
machine. Each mail is stored once in models.plan_evidence (origin 'email'); a difference with the declared plans
becomes a 'plan_change' alert (proposal with buttons), judged on the latest mail of each plan."""
from __future__ import annotations

import html
import json
import re
import subprocess
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from urllib.request import Request, urlopen

from walter_router.research.plans import declared

API = "https://gmail.googleapis.com/gmail/v1/users/me"
GRANT = "google-memory"
VENDORS = {"openai.com": "OpenAI", "anthropic.com": "Anthropic", "x.ai": "xAI", "kie.ai": "Kie", "openrouter.ai": "OpenRouter",
           "google.com": "Google", "cursor.com": "Cursor", "mistral.ai": "Mistral", "perplexity.ai": "Perplexity",
           "midjourney.com": "Midjourney", "suno.com": "Suno", "elevenlabs.io": "ElevenLabs", "runwayml.com": "Runway"}
WORDS = "(receipt OR invoice OR reçu OR facture OR subscription OR abonnement OR renewal OR renouvellement OR " \
        "upgrade OR cancel OR annulation OR welcome OR bienvenue OR essai OR trial OR \"your plan\" OR \"votre forfait\")"
# subscription mails only: the subject or the first lines must speak of a plan, an order, a trial or its end
BILLING = re.compile(r"subscription|abonnement|receipt|reçu|commande|order|confirm|welcome to|bienvenue|essai|trial|"
                     r"cancel|annul|résili|prendr\w* fin|will end|renew|renouvel|upgrade|plan|forfait", re.I)
PRODUCT = {"OpenAI": "ChatGPT", "Anthropic": "Claude", "xAI": "SuperGrok", "Google": "Google AI"}
PLAN = re.compile(r"\b(ChatGPT|Claude|Gemini|Google AI|Google One|SuperGrok|Grok|Cursor|Perplexity|Le Chat|Midjourney|"
                  r"Suno|ElevenLabs|Runway)?\s*(Plus|Pro|Max|Team|Ultra|Premium|Business|Basic|Standard|Enterprise)"
                  r"(?:\s*(\d+x))?\b", re.I)
AMOUNT = re.compile(r"(?:(US\$|\$|€|EUR|USD)\s?(\d{1,4}(?:[.,]\d{2})?))|(?:(\d{1,4}(?:[.,]\d{2})?)\s?(€|EUR|USD|\$))")
CANCEL = re.compile(r"will be cancel|has been cancel|cancell?ed|annulé|résili|prendr\w* fin|avantages .* fin|ended", re.I)
TRIAL = re.compile(r"essai .*se terminera|trial (ends|will end)", re.I)
UPGRADE = re.compile(r"upgrade|vous êtes passé|now on", re.I)
EXPIRED = re.compile(r"a expiré|has expired|expired", re.I)
CREDIT = re.compile(r"credit|crédit|top.?up|balance|recharge|API", re.I)
PAY_AS_YOU_GO = {"OpenRouter", "Kie"}   # credit top-ups, not plans
GOOGLE_BILLING = ("googleplay-noreply@google.com", "payments-noreply@google.com", "googleone-noreply@google.com")
REDACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{6,}\b|\*{2,}\d+|#[\d-]{6,}|\b[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}\b")


def _token() -> str:
    out = subprocess.run(["walter-secret", "grant", "access", GRANT], capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"Gmail grant {GRANT} unavailable")
    return out.stdout.strip()


def _get(token: str, path: str) -> dict:
    req = Request(f"{API}/{path}", headers={"Authorization": f"Bearer {token}"})   # header only, never in a URL
    with urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed Google host)
        return json.loads(resp.read())


def parse(sender: str, subject: str, snippet: str) -> dict | None:
    """vendor, plan, amount, currency, event of one subscription mail (None when it is not one)."""
    sender = (sender or "").lower()
    dom = (re.search(r"@([\w.-]+)", sender) or [None, ""])[1]
    vendor = next((v for d, v in VENDORS.items() if dom == d or dom.endswith("." + d)), None)
    if not vendor or (vendor == "Google" and not any(g in sender for g in GOOGLE_BILLING)):
        return None
    text = f"{subject} {snippet}"
    if not BILLING.search(subject or "") and not BILLING.search((snippet or "")[:160]):
        return None   # newsletters, product news
    if vendor == "Google" and not re.search(r"Google One|Google AI|Gemini", text):
        return None   # Google Cloud invoices, Play terms
    a = AMOUNT.search(text)
    amount = currency = None
    if a:
        cur, num = (a.group(1), a.group(2)) if a.group(2) else (a.group(4), a.group(3))
        amount = float(num.replace(",", "."))
        currency = "EUR" if cur in ("€", "EUR") else "USD"
    if vendor in PAY_AS_YOU_GO or (CREDIT.search(subject or "") and not re.search(r"subscription|abonnement", subject or "", re.I)):
        return {"vendor": vendor, "plan": None, "amount": amount, "currency": currency, "event": "credit"}
    event = "trial_end" if TRIAL.search(text) or (EXPIRED.search(subject or "") and re.search(r"essai|trial", subject or "", re.I)) \
        else "cancel" if CANCEL.search(text) else \
        "upgrade" if UPGRADE.search(text) else "active"
    m = re.search(r"Google AI (Pro|Ultra)", text) if vendor == "Google" else PLAN.search(text)
    if vendor == "Google" and m:
        plan = f"Google AI {m.group(1)}"
    elif m:
        plan = " ".join(x for x in ((m.group(1) or PRODUCT.get(vendor, "")), m.group(2), m.group(3)) if x).strip()
    else:
        plan = None
    return {"vendor": vendor, "plan": plan, "amount": amount, "currency": currency, "event": event}


def _match(found: dict, plans: list[dict]) -> dict | None:
    for s in plans:
        if s.get("vendor", "").lower() == found["vendor"].lower() and (
                not found["plan"] or found["plan"].lower().split()[-1] in s.get("plan", "").lower()):
            return s
    return None


def proposal(found: dict, plans: list[dict]) -> dict | None:
    """What the owner is asked to adopt given the LATEST mail of a plan, or None when it matches what is declared."""
    if found["event"] in ("credit", "trial_end") or not found["plan"]:
        return None
    cur = _match(found, plans)
    since = (cur or {}).get("updated") or (cur or {}).get("declared")
    if cur and since and found.get("date") and found["date"] < since:
        return None   # older than the owner's own declaration of this plan: he already knows better (2026-10-22)
    if found["event"] == "cancel":
        return {"action": "retire", "sub_id": cur["id"], "text": f"{cur['vendor']} {cur['plan']} résilié"} if cur else None
    if cur is None:
        sid = re.sub(r"[^a-z0-9]+", "-", f"{found['vendor']} {found['plan']}".lower()).strip("-")
        fields = {"vendor": found["vendor"], "plan": found["plan"], "price_usd_month": found["amount"] or 0}
        if found["currency"] == "EUR":
            fields["note"] = f"payé {found['amount']} € (montant du mail ; prix en dollars à confirmer)"
        return {"action": "upsert", "sub_id": sid, "fields": fields, "text": f"nouvel abonnement {found['vendor']} {found['plan']}"}
    if found["amount"] and found["currency"] == "USD" and abs(found["amount"] - float(cur["price_usd_month"])) >= 0.5:
        return {"action": "upsert", "sub_id": cur["id"], "fields": {"price_usd_month": found["amount"]},
                "text": f"{cur['vendor']} {cur['plan']} : {cur['price_usd_month']} $ → {found['amount']} $"}
    return None


def scan(conn, days: int = 120) -> dict:
    """Read the vendors' subscription mails of the last `days`; store each once; propose on the LATEST event per plan."""
    token = _token()
    q = "from:(" + " OR ".join(VENDORS) + f") {WORDS} newer_than:{days}d"
    ids = [m["id"] for m in _get(token, f"messages?maxResults=100&q={quote(q)}").get("messages", [])]
    seen = {r["source_url"] for r in conn.execute("select source_url from models.plan_evidence where origin = 'email'")}
    plans = declared.read().get("subscriptions", [])
    out = {"mails": len(ids), "subscription_mails": 0, "new": 0, "proposals": []}
    latest: dict[tuple, tuple] = {}
    for mid in ids:
        m = _get(token, f"messages/{mid}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        found = parse(h.get("from", ""), h.get("subject", ""), m.get("snippet", ""))
        if not found:
            continue
        out["subscription_mails"] += 1
        try:
            when = parsedate_to_datetime(h["date"])
        except Exception:  # noqa: BLE001
            continue
        quote_txt = REDACT.sub("…", html.unescape(f'{h.get("subject", "")} — {m.get("snippet", "")}'))[:300]
        if found["plan"]:
            key = (found["vendor"], found["plan"])
            if key not in latest or when > latest[key][0]:
                latest[key] = (when, found, quote_txt)
        ref = f"gmail:{mid}"
        if ref in seen:
            continue
        sub = _match(found, plans) if found["plan"] else None
        conn.execute("""insert into models.plan_evidence (sub_id, vendor, plan, metric, value, unit, source_name, source_url,
                        published, quote, origin) values (%s,%s,%s,'plan_change',%s,%s,%s,%s,%s,%s,'email') on conflict do nothing""",
                     (sub["id"] if sub else None, found["vendor"], found["plan"] or "crédit", found["amount"],
                      found["currency"], f"mail {found['vendor']} ({found['event']})", ref, when.date(), quote_txt))
        out["new"] += 1
    from walter_router.analysis.alerts import _upsert
    for (vendor, plan), (when, found, quote_txt) in latest.items():
        p = proposal({**found, "date": when.date().isoformat()}, plans)
        if p:
            ev = {**p, "mail_date": str(when.date()), "vendor": vendor, "plan": plan, "amount": found["amount"],
                  "currency": found["currency"], "event": found["event"], "quote": quote_txt}
            if _upsert(conn, "plan_change", "", f"{p['sub_id']}:{p['action']}:{found['amount']}", ev, "open"):
                out["proposals"].append(p["text"])
    out["latest"] = {f"{v} {p}": f"{f['event']} {w.date()}" for (v, p), (w, f, _) in latest.items()}
    return out
